"""Tenant-scoped integration registry and idempotent workflow trigger hub."""
from __future__ import annotations

import json
import hashlib
import hmac
import os
import base64
import secrets
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urlparse

from infrastructure.people_ops_store import DEPARTMENTS, PLAYBOOKS, PeopleOpsError, get_people_ops_store
from infrastructure.job_queue import get_job_queue
from infrastructure.secret_vault import SecretVaultError, get_secret_vault


INTEGRATION_CATALOG: dict[str, dict[str, Any]] = {
    "slack": {"name": "Slack", "category": "collaboration", "auth_modes": ["oauth", "sandbox"], "triggers": ["message", "slash_command"]},
    "google_workspace": {"name": "Google Workspace", "category": "productivity", "auth_modes": ["oauth", "service_account", "sandbox"], "triggers": ["drive_change", "calendar_event", "gmail_message"]},
    "microsoft_365": {"name": "Microsoft 365", "category": "productivity", "auth_modes": ["oauth", "service_account", "sandbox"], "triggers": ["sharepoint_change", "calendar_event", "email"]},
    "hubspot": {"name": "HubSpot", "category": "crm", "auth_modes": ["oauth", "api_key_ref", "sandbox"], "triggers": ["contact_change", "deal_change"]},
    "salesforce": {"name": "Salesforce", "category": "crm", "auth_modes": ["oauth", "sandbox"], "triggers": ["lead_change", "opportunity_change"]},
    "gusto": {"name": "Gusto", "category": "hris", "auth_modes": ["oauth", "sandbox"], "triggers": ["employee_change"]},
    "rippling": {"name": "Rippling", "category": "hris", "auth_modes": ["oauth", "api_key_ref", "sandbox"], "triggers": ["employee_change"]},
    "quickbooks": {"name": "QuickBooks", "category": "accounting", "auth_modes": ["oauth", "sandbox"], "triggers": ["invoice_change", "close_event"]},
    "xero": {"name": "Xero", "category": "accounting", "auth_modes": ["oauth", "sandbox"], "triggers": ["invoice_change", "close_event"]},
    "postgres": {"name": "PostgreSQL", "category": "database", "auth_modes": ["secret_ref", "sandbox"], "triggers": ["query_schedule", "webhook"]},
    "mysql": {"name": "MySQL", "category": "database", "auth_modes": ["secret_ref", "sandbox"], "triggers": ["query_schedule", "webhook"]},
    "snowflake": {"name": "Snowflake", "category": "warehouse", "auth_modes": ["secret_ref", "oauth", "sandbox"], "triggers": ["query_schedule", "webhook"]},
    "jira": {"name": "Jira", "category": "ticketing", "auth_modes": ["oauth", "api_key_ref", "sandbox"], "triggers": ["issue_change"]},
    "linear": {"name": "Linear", "category": "ticketing", "auth_modes": ["oauth", "api_key_ref", "sandbox"], "triggers": ["issue_change"]},
    "zendesk": {"name": "Zendesk", "category": "support", "auth_modes": ["oauth", "api_key_ref", "sandbox"], "triggers": ["ticket_change"]},
    "docusign": {"name": "DocuSign", "category": "e_sign", "auth_modes": ["oauth", "sandbox"], "triggers": ["envelope_change"]},
    "github": {"name": "GitHub", "category": "engineering", "auth_modes": ["oauth", "app_secret_ref", "sandbox"], "triggers": ["pull_request", "release"]},
}


class IntegrationHubError(ValueError):
    """Safe integration contract error."""


class IntegrationHub:
    def __init__(self, db_path: str | None = None):
        self.db_path = Path(db_path or os.getenv("RAPID_INTEGRATIONS_DB_PATH", "data/db/integrations.db"))
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=30)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        conn = self._connect()
        try:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS integration_connections (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    department TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    label TEXT NOT NULL,
                    auth_mode TEXT NOT NULL,
                    credential_ref TEXT NOT NULL DEFAULT '',
                    config_json TEXT NOT NULL DEFAULT '{}',
                    status TEXT NOT NULL,
                    created_by TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(tenant_id, department, label)
                );
                CREATE INDEX IF NOT EXISTS idx_integration_scope
                    ON integration_connections(tenant_id, department, status);
                CREATE TABLE IF NOT EXISTS integration_events (
                    id TEXT PRIMARY KEY,
                    connection_id TEXT NOT NULL,
                    tenant_id TEXT NOT NULL,
                    department TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    run_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(connection_id, idempotency_key)
                );
                CREATE INDEX IF NOT EXISTS idx_integration_events_scope
                    ON integration_events(tenant_id, department, created_at DESC);
                CREATE TABLE IF NOT EXISTS automation_schedules (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    department TEXT NOT NULL,
                    connection_id TEXT NOT NULL,
                    playbook_key TEXT NOT NULL,
                    subject_name TEXT NOT NULL,
                    subject_email TEXT NOT NULL DEFAULT '',
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    interval_minutes INTEGER NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    next_run_at TEXT NOT NULL,
                    last_run_at TEXT,
                    last_status TEXT NOT NULL DEFAULT 'pending',
                    last_error TEXT NOT NULL DEFAULT '',
                    created_by TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_automation_schedules_due
                    ON automation_schedules(tenant_id, enabled, next_run_at);
                CREATE TABLE IF NOT EXISTS integration_oauth_states (
                    state TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    connection_id TEXT NOT NULL,
                    code_verifier TEXT NOT NULL,
                    redirect_uri TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _safe_config(config: dict[str, Any] | None) -> dict[str, Any]:
        values = dict(config or {})
        sensitive = {"password", "token", "secret", "api_key", "access_token", "refresh_token", "private_key"}
        if sensitive & {str(key).lower() for key in values}:
            raise IntegrationHubError("Store credentials in a secret manager and pass only a credential reference")
        return values

    def list_catalog(self) -> list[dict]:
        return [{"key": key, **value} for key, value in INTEGRATION_CATALOG.items()]

    def register_connection(self, tenant_id: str, department: str, provider: str, label: str, auth_mode: str,
                            credential_ref: str, config: dict[str, Any] | None, created_by: str) -> dict:
        if department not in DEPARTMENTS:
            raise IntegrationHubError("Unknown department")
        definition = INTEGRATION_CATALOG.get(provider)
        if not definition:
            raise IntegrationHubError("Unknown integration provider")
        if auth_mode not in definition["auth_modes"]:
            raise IntegrationHubError("This provider does not support the requested authentication mode")
        if auth_mode != "sandbox" and not credential_ref.strip() and not str((config or {}).get("client_secret_ref") or "").strip():
            raise IntegrationHubError("A secret-manager credential reference is required for live connections")
        if not label.strip() or len(label) > 160:
            raise IntegrationHubError("A connection label between 1 and 160 characters is required")
        config = self._safe_config(config)
        now = self._now()
        connection_id = f"int_{uuid.uuid4().hex[:12]}"
        status = "sandbox_ready" if auth_mode == "sandbox" else "needs_verification"
        conn = self._connect()
        try:
            conn.execute(
                """INSERT INTO integration_connections
                   (id, tenant_id, department, provider, label, auth_mode, credential_ref, config_json, status, created_by, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (connection_id, tenant_id, department, provider, label.strip(), auth_mode, credential_ref.strip(), json.dumps(config), status, created_by, now, now),
            )
            conn.commit()
        except sqlite3.IntegrityError as error:
            raise IntegrationHubError("A connection with this label already exists in the department") from error
        finally:
            conn.close()
        return self.get_connection(tenant_id, connection_id)

    def _row(self, conn: sqlite3.Connection, tenant_id: str, connection_id: str) -> sqlite3.Row:
        row = conn.execute("SELECT * FROM integration_connections WHERE id=? AND tenant_id=?", (connection_id, tenant_id)).fetchone()
        if not row:
            raise IntegrationHubError("Integration connection not found")
        return row

    def _serialize(self, row: sqlite3.Row) -> dict:
        data = dict(row)
        data["config"] = json.loads(data.pop("config_json") or "{}")
        data["credential_configured"] = bool(data.pop("credential_ref", ""))
        data["provider_name"] = INTEGRATION_CATALOG[data["provider"]]["name"]
        return data

    def get_connection(self, tenant_id: str, connection_id: str) -> dict:
        conn = self._connect()
        try:
            return self._serialize(self._row(conn, tenant_id, connection_id))
        finally:
            conn.close()

    def get_connection_by_id(self, connection_id: str) -> dict:
        conn = self._connect()
        try:
            row = conn.execute("SELECT * FROM integration_connections WHERE id=?", (connection_id,)).fetchone()
            if not row:
                raise IntegrationHubError("Integration connection not found")
            return self._serialize(row)
        finally:
            conn.close()

    def _raw_connection(self, connection_id: str) -> sqlite3.Row:
        conn = self._connect()
        try:
            row = conn.execute("SELECT * FROM integration_connections WHERE id=?", (connection_id,)).fetchone()
            if not row:
                raise IntegrationHubError("Integration connection not found")
            return row
        finally:
            conn.close()

    def receive_webhook(
        self,
        connection_id: str,
        body: bytes,
        signature: str,
        timestamp: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        if len(body) > 1_000_000:
            raise IntegrationHubError("Webhook payload must be smaller than 1MB")
        row = self._raw_connection(connection_id)
        config = json.loads(row["config_json"] or "{}")
        if row["status"] not in {"sandbox_ready", "connected"}:
            raise IntegrationHubError("Integration connection is not ready")
        try:
            sent_at = datetime.fromtimestamp(float(timestamp), timezone.utc)
        except (TypeError, ValueError, OverflowError) as error:
            raise IntegrationHubError("Webhook timestamp is invalid") from error
        if abs((datetime.now(timezone.utc) - sent_at).total_seconds()) > 300:
            raise IntegrationHubError("Webhook timestamp is outside the five-minute replay window")
        secret_ref = str(config.get("webhook_secret_ref") or row["credential_ref"] or "")
        allow_unsigned_sandbox = row["auth_mode"] == "sandbox" and os.getenv(
            "RAPID_ALLOW_UNSIGNED_SANDBOX_WEBHOOKS", "true" if os.getenv("RAPID_ENV", "development") != "production" else "false"
        ).lower() in {"1", "true", "yes"}
        if secret_ref:
            try:
                secret = get_secret_vault().resolve(secret_ref, row["tenant_id"])
            except SecretVaultError as error:
                raise IntegrationHubError(str(error)) from error
            expected = "sha256=" + hmac.new(secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256).hexdigest()
            if not hmac.compare_digest(signature, expected):
                raise IntegrationHubError("Webhook signature verification failed")
        elif not allow_unsigned_sandbox:
            raise IntegrationHubError("A webhook secret reference is required")
        try:
            payload = json.loads(body or b"{}")
        except json.JSONDecodeError as error:
            raise IntegrationHubError("Webhook body must be valid JSON") from error
        if not isinstance(payload, dict):
            raise IntegrationHubError("Webhook body must be a JSON object")
        key = idempotency_key.strip() or hashlib.sha256(body).hexdigest()
        job = get_job_queue().enqueue(
            row["tenant_id"], "integration.webhook",
            {"connection_id": connection_id, "payload": payload, "received_at": self._now()},
            idempotency_key=f"webhook:{connection_id}:{key}",
        )
        return {"accepted": True, "duplicate": job["duplicate"], "job_id": job["id"]}

    def process_webhook_job(self, tenant_id: str, job_payload: dict[str, Any]) -> dict[str, Any]:
        connection_id = str(job_payload.get("connection_id") or "")
        payload = job_payload.get("payload") or {}
        row = self._raw_connection(connection_id)
        if row["tenant_id"] != tenant_id:
            raise IntegrationHubError("Webhook job is outside this tenant")
        config = json.loads(row["config_json"] or "{}")
        playbook_key = str(config.get("playbook_key") or payload.get("playbook_key") or "")
        if playbook_key not in PLAYBOOKS:
            raise IntegrationHubError("Webhook connection needs a configured playbook_key")
        subject_field = str(config.get("subject_field") or "subject_name")
        subject_name = str(payload.get(subject_field) or payload.get("name") or f"{row['provider']} webhook")[:160]
        subject_email = str(payload.get(str(config.get("email_field") or "subject_email")) or "")[:254]
        event_type = str(payload.get(str(config.get("event_type_field") or "event_type")) or "webhook")[:100]
        event_key = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()
        result = self.trigger_event(
            tenant_id, connection_id, f"webhook-job:{event_key}", event_type, playbook_key,
            subject_name, subject_email, payload, "integration-webhook",
        )
        return {"connection_id": connection_id, "run_id": result["run"]["id"], "duplicate": result["duplicate"]}

    @staticmethod
    def _validate_oauth_url(value: str, label: str) -> str:
        parsed = urlparse(value)
        development_local = os.getenv("RAPID_ENV", "development") != "production" and parsed.hostname in {"127.0.0.1", "localhost"}
        if parsed.scheme != "https" and not development_local:
            raise IntegrationHubError(f"{label} must use HTTPS")
        if not parsed.netloc:
            raise IntegrationHubError(f"{label} is invalid")
        return value

    def create_oauth_authorization(self, tenant_id: str, connection_id: str) -> dict[str, Any]:
        row = self._raw_connection(connection_id)
        if row["tenant_id"] != tenant_id:
            raise IntegrationHubError("Integration connection not found")
        if row["auth_mode"] != "oauth":
            raise IntegrationHubError("This connection is not configured for OAuth")
        config = json.loads(row["config_json"] or "{}")
        authorize_url = self._validate_oauth_url(str(config.get("authorize_url") or ""), "OAuth authorization URL")
        client_id = str(config.get("client_id") or "").strip()
        redirect_uri = str(config.get("redirect_uri") or "").strip()
        if not client_id or not redirect_uri:
            raise IntegrationHubError("OAuth client_id and redirect_uri are required")
        state = secrets.token_urlsafe(32)
        verifier = secrets.token_urlsafe(64)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
        now = datetime.now(timezone.utc)
        conn = self._connect()
        try:
            conn.execute("DELETE FROM integration_oauth_states WHERE expires_at<?", (now.isoformat(),))
            conn.execute(
                "INSERT INTO integration_oauth_states VALUES (?,?,?,?,?,?,?)",
                (state, tenant_id, connection_id, verifier, redirect_uri, (now + timedelta(minutes=10)).isoformat(), now.isoformat()),
            )
            conn.commit()
        finally:
            conn.close()
        params = {
            "response_type": "code", "client_id": client_id, "redirect_uri": redirect_uri, "state": state,
            "code_challenge": challenge, "code_challenge_method": "S256",
        }
        scopes = config.get("scopes") or []
        if scopes:
            params["scope"] = " ".join(str(scope) for scope in scopes)
        return {"authorization_url": f"{authorize_url}?{urlencode(params)}", "expires_in": 600, "connection_id": connection_id}

    def consume_oauth_state(self, state: str) -> dict[str, Any]:
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT * FROM integration_oauth_states WHERE state=?", (state,)).fetchone()
            if not row:
                raise IntegrationHubError("OAuth state is invalid or already used")
            conn.execute("DELETE FROM integration_oauth_states WHERE state=?", (state,))
            conn.commit()
            if datetime.fromisoformat(row["expires_at"]) < datetime.now(timezone.utc):
                raise IntegrationHubError("OAuth state has expired")
            return dict(row)
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def oauth_exchange_config(self, state_record: dict[str, Any]) -> dict[str, Any]:
        row = self._raw_connection(state_record["connection_id"])
        if row["tenant_id"] != state_record["tenant_id"]:
            raise IntegrationHubError("OAuth state tenant mismatch")
        config = json.loads(row["config_json"] or "{}")
        token_url = self._validate_oauth_url(str(config.get("token_url") or ""), "OAuth token URL")
        client_secret_ref = str(config.get("client_secret_ref") or row["credential_ref"] or "")
        return {
            "tenant_id": row["tenant_id"], "connection_id": row["id"], "token_url": token_url,
            "client_id": str(config.get("client_id") or ""), "client_secret_ref": client_secret_ref,
            "redirect_uri": state_record["redirect_uri"], "code_verifier": state_record["code_verifier"],
        }

    def mark_oauth_connected(self, tenant_id: str, connection_id: str, token_reference: str) -> dict[str, Any]:
        conn = self._connect()
        try:
            result = conn.execute(
                "UPDATE integration_connections SET credential_ref=?, status='connected', updated_at=? WHERE id=? AND tenant_id=?",
                (token_reference, self._now(), connection_id, tenant_id),
            )
            if not result.rowcount:
                raise IntegrationHubError("Integration connection not found")
            conn.commit()
        finally:
            conn.close()
        return self.get_connection(tenant_id, connection_id)

    def list_connections(self, tenant_id: str, department: str | None = None) -> list[dict]:
        conn = self._connect()
        try:
            query = "SELECT * FROM integration_connections WHERE tenant_id=?"
            args: list[Any] = [tenant_id]
            if department:
                query += " AND department=?"
                args.append(department)
            query += " ORDER BY created_at DESC"
            return [self._serialize(row) for row in conn.execute(query, args).fetchall()]
        finally:
            conn.close()

    def test_connection(self, tenant_id: str, connection_id: str) -> dict:
        conn = self._connect()
        try:
            row = self._row(conn, tenant_id, connection_id)
            status = "sandbox_ready" if row["auth_mode"] == "sandbox" else "needs_verification"
            conn.execute("UPDATE integration_connections SET status=?, updated_at=? WHERE id=? AND tenant_id=?", (status, self._now(), connection_id, tenant_id))
            conn.commit()
            return {"connection": self._serialize(self._row(conn, tenant_id, connection_id)), "result": "sandbox verified" if status == "sandbox_ready" else "credential reference recorded; provider verification required"}
        finally:
            conn.close()

    def trigger_event(self, tenant_id: str, connection_id: str, idempotency_key: str, event_type: str,
                      playbook_key: str, subject_name: str, subject_email: str, payload: dict[str, Any], actor: str) -> dict:
        if not idempotency_key.strip() or len(idempotency_key) > 255:
            raise IntegrationHubError("An idempotency key is required")
        if playbook_key not in PLAYBOOKS:
            raise IntegrationHubError("Unknown organization playbook")
        conn = self._connect()
        try:
            connection = self._row(conn, tenant_id, connection_id)
            if connection["status"] not in {"sandbox_ready", "connected"}:
                raise IntegrationHubError("Integration connection is not ready")
            if PLAYBOOKS[playbook_key]["department"] != connection["department"]:
                raise IntegrationHubError("Integration events can only trigger playbooks in their department")
            duplicate = conn.execute("SELECT run_id FROM integration_events WHERE connection_id=? AND idempotency_key=?", (connection_id, idempotency_key)).fetchone()
            if duplicate:
                run = get_people_ops_store().get_run(tenant_id, duplicate["run_id"])
                return {"run": run, "duplicate": True}
            try:
                run = get_people_ops_store().create_run(tenant_id, actor, playbook_key, subject_name, subject_email, details={"integration_event": payload, "event_type": event_type, "connection_id": connection_id})
                run = get_people_ops_store().advance_to_gate(tenant_id, run["id"], actor)
            except PeopleOpsError as error:
                raise IntegrationHubError(str(error)) from error
            conn.execute(
                """INSERT INTO integration_events
                   (id, connection_id, tenant_id, department, idempotency_key, event_type, payload_json, run_id, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (f"evt_{uuid.uuid4().hex[:12]}", connection_id, tenant_id, connection["department"], idempotency_key, event_type, json.dumps(payload), run["id"], self._now()),
            )
            conn.commit()
            return {"run": run, "duplicate": False}
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def create_schedule(self, tenant_id: str, connection_id: str, playbook_key: str, subject_name: str,
                        subject_email: str, payload: dict[str, Any], interval_minutes: int, created_by: str) -> dict:
        if interval_minutes < 5 or interval_minutes > 43_200:
            raise IntegrationHubError("Schedule interval must be between 5 minutes and 30 days")
        if playbook_key not in PLAYBOOKS:
            raise IntegrationHubError("Unknown organization playbook")
        if not subject_name.strip():
            raise IntegrationHubError("A schedule subject is required")
        payload = self._safe_config(payload)
        conn = self._connect()
        try:
            connection = self._row(conn, tenant_id, connection_id)
            if connection["status"] not in {"sandbox_ready", "connected"}:
                raise IntegrationHubError("Integration connection is not ready")
            if PLAYBOOKS[playbook_key]["department"] != connection["department"]:
                raise IntegrationHubError("A schedule can only trigger playbooks in its connection department")
            now = self._now()
            schedule_id = f"sch_{uuid.uuid4().hex[:12]}"
            conn.execute(
                """INSERT INTO automation_schedules
                   (id, tenant_id, department, connection_id, playbook_key, subject_name, subject_email, payload_json,
                    interval_minutes, next_run_at, created_by, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (schedule_id, tenant_id, connection["department"], connection_id, playbook_key, subject_name.strip(),
                 subject_email.strip(), json.dumps(payload), interval_minutes, now, created_by, now, now),
            )
            conn.commit()
            return self._serialize_schedule(self._schedule_row(conn, tenant_id, schedule_id))
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _schedule_row(self, conn: sqlite3.Connection, tenant_id: str, schedule_id: str) -> sqlite3.Row:
        row = conn.execute("SELECT * FROM automation_schedules WHERE id=? AND tenant_id=?", (schedule_id, tenant_id)).fetchone()
        if not row:
            raise IntegrationHubError("Automation schedule not found")
        return row

    @staticmethod
    def _serialize_schedule(row: sqlite3.Row) -> dict:
        data = dict(row)
        data["payload"] = json.loads(data.pop("payload_json") or "{}")
        data["enabled"] = bool(data["enabled"])
        return data

    def get_schedule(self, tenant_id: str, schedule_id: str) -> dict:
        conn = self._connect()
        try:
            return self._serialize_schedule(self._schedule_row(conn, tenant_id, schedule_id))
        finally:
            conn.close()

    def list_schedules(self, tenant_id: str, department: str | None = None) -> list[dict]:
        conn = self._connect()
        try:
            query = "SELECT * FROM automation_schedules WHERE tenant_id=?"
            args: list[Any] = [tenant_id]
            if department:
                query += " AND department=?"
                args.append(department)
            query += " ORDER BY next_run_at ASC"
            return [self._serialize_schedule(row) for row in conn.execute(query, args).fetchall()]
        finally:
            conn.close()

    def set_schedule_enabled(self, tenant_id: str, schedule_id: str, enabled: bool) -> dict:
        conn = self._connect()
        try:
            self._schedule_row(conn, tenant_id, schedule_id)
            conn.execute(
                "UPDATE automation_schedules SET enabled=?, updated_at=? WHERE id=? AND tenant_id=?",
                (int(enabled), self._now(), schedule_id, tenant_id),
            )
            conn.commit()
            return self._serialize_schedule(self._schedule_row(conn, tenant_id, schedule_id))
        finally:
            conn.close()

    def dispatch_due_schedules(self, tenant_id: str | None = None, now: datetime | None = None) -> list[dict]:
        """Claim due schedules before execution so multiple workers cannot dispatch the same interval."""
        now = now or datetime.now(timezone.utc)
        now_value = now.isoformat()
        conn = self._connect()
        claimed: list[dict] = []
        try:
            conn.execute("BEGIN IMMEDIATE")
            query = "SELECT * FROM automation_schedules WHERE enabled=1 AND next_run_at<=?"
            args: list[Any] = [now_value]
            if tenant_id:
                query += " AND tenant_id=?"
                args.append(tenant_id)
            for row in conn.execute(query, args).fetchall():
                next_run_at = datetime.fromisoformat(row["next_run_at"])
                following = (next_run_at + timedelta(minutes=row["interval_minutes"])).isoformat()
                conn.execute(
                    """UPDATE automation_schedules
                       SET next_run_at=?, last_run_at=?, last_status='running', last_error='', updated_at=?
                       WHERE id=? AND tenant_id=?""",
                    (following, now_value, now_value, row["id"], row["tenant_id"]),
                )
                claimed.append(dict(row))
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

        results: list[dict] = []
        for schedule in claimed:
            idempotency_key = f"schedule:{schedule['id']}:{schedule['next_run_at']}"
            try:
                result = self.trigger_event(
                    tenant_id=schedule["tenant_id"], connection_id=schedule["connection_id"],
                    idempotency_key=idempotency_key, event_type="scheduled", playbook_key=schedule["playbook_key"],
                    subject_name=schedule["subject_name"], subject_email=schedule["subject_email"],
                    payload=json.loads(schedule["payload_json"] or "{}"), actor="automation-scheduler",
                )
                status, error = "dispatched", ""
                results.append({"schedule_id": schedule["id"], "run_id": result["run"]["id"], "duplicate": result["duplicate"], "status": status})
            except IntegrationHubError as exc:
                status, error = "failed", str(exc)
                results.append({"schedule_id": schedule["id"], "status": status, "error": error})
            conn = self._connect()
            try:
                conn.execute(
                    "UPDATE automation_schedules SET last_status=?, last_error=?, updated_at=? WHERE id=? AND tenant_id=?",
                    (status, error, self._now(), schedule["id"], schedule["tenant_id"]),
                )
                conn.commit()
            finally:
                conn.close()
        return results


def get_integration_hub() -> IntegrationHub:
    return IntegrationHub()
