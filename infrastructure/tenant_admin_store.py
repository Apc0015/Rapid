"""Configuration-first tenant administration without storing raw credentials."""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


FEATURES = {
    "meetings": "Meetings and decisions",
    "workflows": "Governed workflows",
    "knowledge": "Knowledge and RAG",
    "automations": "Automations and schedules",
    "integrations": "Integration hub",
    "reports": "Department reports",
    "projects": "Projects and delivery",
    "people": "People directory",
    "crm": "Customer operations",
    "tickets": "Service operations",
}
MODEL_PROVIDERS = {"ollama", "openrouter"}
CONNECTION_KINDS = {"database", "sso", "integration", "storage", "email"}
logger = logging.getLogger(__name__)


class TenantAdminError(ValueError):
    """Safe administration configuration error."""


class TenantAdminStore:
    def __init__(self, db_path: str | None = None):
        self.db_path = Path(db_path or os.getenv("RAPID_TENANT_ADMIN_DB_PATH", "data/db/tenant_admin.db"))
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
                CREATE TABLE IF NOT EXISTS tenant_features (
                    tenant_id TEXT NOT NULL, feature_key TEXT NOT NULL, enabled INTEGER NOT NULL,
                    updated_at TEXT NOT NULL, PRIMARY KEY (tenant_id, feature_key)
                );
                CREATE TABLE IF NOT EXISTS tenant_models (
                    tenant_id TEXT NOT NULL, provider TEXT NOT NULL, enabled INTEGER NOT NULL,
                    model_name TEXT NOT NULL, endpoint TEXT NOT NULL, credential_ref TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL, PRIMARY KEY (tenant_id, provider)
                );
                CREATE TABLE IF NOT EXISTS tenant_connections (
                    tenant_id TEXT NOT NULL, connection_key TEXT NOT NULL, kind TEXT NOT NULL, enabled INTEGER NOT NULL,
                    label TEXT NOT NULL, configuration_json TEXT NOT NULL DEFAULT '{}', credential_ref TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL, updated_at TEXT NOT NULL, PRIMARY KEY (tenant_id, connection_key)
                );
                CREATE TABLE IF NOT EXISTS tenant_invitations (
                    id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, email TEXT NOT NULL, name TEXT NOT NULL,
                    role TEXT NOT NULL, departments_json TEXT NOT NULL, status TEXT NOT NULL,
                    created_at TEXT NOT NULL, UNIQUE(tenant_id, email)
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
    def _safe_config(values: dict[str, Any]) -> dict[str, Any]:
        prohibited = {"password", "token", "secret", "api_key", "private_key", "access_token", "refresh_token"}
        if prohibited & {str(key).lower() for key in values}:
            raise TenantAdminError("Store credentials in a secret manager and provide only a credential reference")
        return values

    def ensure_tenant(self, tenant_id: str) -> None:
        conn = self._connect()
        try:
            now = self._now()
            for key in FEATURES:
                conn.execute("INSERT OR IGNORE INTO tenant_features VALUES (?,?,?,?)", (tenant_id, key, 1, now))
            models = [("ollama", 1, "llama3.1:8b", "http://localhost:11434", ""), ("openrouter", 0, "", "https://openrouter.ai/api/v1", "")]
            for provider, enabled, model, endpoint, credential_ref in models:
                conn.execute("INSERT OR IGNORE INTO tenant_models VALUES (?,?,?,?,?,?,?)", (tenant_id, provider, enabled, model, endpoint, credential_ref, now))
            defaults = [
                ("sso", "sso", "Single sign-on", {"provider": "not_configured"}, "not_configured"),
                ("primary_database", "database", "Primary business database", {"engine": "postgres"}, "not_configured"),
                ("knowledge_storage", "storage", "Knowledge storage", {"provider": "local_sandbox"}, "sandbox_ready"),
                ("collaboration", "integration", "Collaboration workspace", {"provider": "slack"}, "not_configured"),
            ]
            for key, kind, label, config, status in defaults:
                conn.execute("INSERT OR IGNORE INTO tenant_connections VALUES (?,?,?,?,?,?,?,?,?)", (tenant_id, key, kind, 0, label, json.dumps(config), "", status, now))
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def _sync_llm_runtime(tenant_id: str, provider: str, model_name: str, endpoint: str, credential_ref: str) -> None:
        """Persist the selected provider for request-time tenant LLM routing."""
        try:
            from infrastructure.llm_adapter import invalidate_tenant_adapter
            from infrastructure.tenant_manager import get_tenant_manager

            manager = get_tenant_manager()
            if not manager.get_tenant(tenant_id):
                manager.create_tenant(tenant_id=tenant_id, company_name=f"{tenant_id.title()} Organization", industry="technology", plan="trial")
            manager.update_tenant(
                tenant_id,
                llm_provider=provider,
                llm_model=model_name,
                llm_config=json.dumps({"base_url": endpoint, "credential_ref": credential_ref}),
            )
            invalidate_tenant_adapter(tenant_id)
        except Exception as error:
            logger.warning("Tenant LLM runtime sync failed for %s: %s", tenant_id, error)

    def configuration(self, tenant_id: str) -> dict[str, Any]:
        self.ensure_tenant(tenant_id)
        conn = self._connect()
        try:
            features = [{"key": row["feature_key"], "name": FEATURES[row["feature_key"]], "enabled": bool(row["enabled"]), "updated_at": row["updated_at"]} for row in conn.execute("SELECT * FROM tenant_features WHERE tenant_id=? ORDER BY feature_key", (tenant_id,))]
            models = [dict(row) for row in conn.execute("SELECT * FROM tenant_models WHERE tenant_id=? ORDER BY provider", (tenant_id,))]
            for model in models:
                model["enabled"] = bool(model["enabled"])
                model["credential_configured"] = bool(model.pop("credential_ref"))
            connections = [dict(row) for row in conn.execute("SELECT * FROM tenant_connections WHERE tenant_id=? ORDER BY connection_key", (tenant_id,))]
            for connection in connections:
                connection["enabled"] = bool(connection["enabled"])
                connection["configuration"] = json.loads(connection.pop("configuration_json") or "{}")
                connection["credential_configured"] = bool(connection.pop("credential_ref"))
            return {"features": features, "models": models, "connections": connections}
        finally:
            conn.close()

    def update_feature(self, tenant_id: str, key: str, enabled: bool) -> dict[str, Any]:
        if key not in FEATURES:
            raise TenantAdminError("Unknown product feature")
        self.ensure_tenant(tenant_id)
        conn = self._connect()
        try:
            conn.execute("UPDATE tenant_features SET enabled=?, updated_at=? WHERE tenant_id=? AND feature_key=?", (int(enabled), self._now(), tenant_id, key))
            conn.commit()
            return {"key": key, "name": FEATURES[key], "enabled": enabled}
        finally:
            conn.close()

    def feature_manifest(self, tenant_id: str) -> list[dict[str, Any]]:
        """Return tenant feature visibility without exposing configuration or credentials."""
        self.ensure_tenant(tenant_id)
        conn = self._connect()
        try:
            return [
                {"key": row["feature_key"], "enabled": bool(row["enabled"])}
                for row in conn.execute(
                    "SELECT feature_key, enabled FROM tenant_features WHERE tenant_id=? ORDER BY feature_key",
                    (tenant_id,),
                )
            ]
        finally:
            conn.close()

    def update_model(self, tenant_id: str, provider: str, enabled: bool, model_name: str, endpoint: str, credential_ref: str) -> dict[str, Any]:
        if provider not in MODEL_PROVIDERS:
            raise TenantAdminError("Unsupported model provider")
        if len(model_name) > 160 or len(endpoint) > 500 or len(credential_ref) > 255:
            raise TenantAdminError("Model configuration exceeds the allowed length")
        if enabled and provider == "openrouter" and not credential_ref.strip():
            raise TenantAdminError("OpenRouter requires a secret-manager credential reference when enabled")
        self.ensure_tenant(tenant_id)
        conn = self._connect()
        try:
            if enabled:
                conn.execute("UPDATE tenant_models SET enabled=0, updated_at=? WHERE tenant_id=?", (self._now(), tenant_id))
            conn.execute("UPDATE tenant_models SET enabled=?, model_name=?, endpoint=?, credential_ref=?, updated_at=? WHERE tenant_id=? AND provider=?", (int(enabled), model_name.strip(), endpoint.strip(), credential_ref.strip(), self._now(), tenant_id, provider))
            conn.commit()
        finally:
            conn.close()
        if enabled:
            self._sync_llm_runtime(tenant_id, provider, model_name.strip(), endpoint.strip(), credential_ref.strip())
        return [item for item in self.configuration(tenant_id)["models"] if item["provider"] == provider][0]

    def active_model_runtime(self, tenant_id: str) -> dict[str, Any]:
        """Internal runtime configuration; credential references are never returned by API serializers."""
        self.ensure_tenant(tenant_id)
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM tenant_models WHERE tenant_id=? AND enabled=1 ORDER BY updated_at DESC LIMIT 1",
                (tenant_id,),
            ).fetchone()
            if not row:
                raise TenantAdminError("No AI model provider is enabled for this tenant")
            return dict(row)
        finally:
            conn.close()

    def update_connection(self, tenant_id: str, key: str, kind: str, enabled: bool, label: str, configuration: dict[str, Any], credential_ref: str) -> dict[str, Any]:
        if kind not in CONNECTION_KINDS or not key.replace("_", "").replace("-", "").isalnum():
            raise TenantAdminError("Invalid connection type or key")
        if not label.strip() or len(label) > 160 or len(credential_ref) > 255:
            raise TenantAdminError("Connection label or credential reference is invalid")
        configuration = self._safe_config(configuration)
        self.ensure_tenant(tenant_id)
        status = "sandbox_ready" if configuration.get("provider") == "local_sandbox" else ("needs_credentials" if enabled and not credential_ref.strip() else "configured")
        conn = self._connect()
        try:
            conn.execute(
                """INSERT INTO tenant_connections VALUES (?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(tenant_id, connection_key) DO UPDATE SET kind=excluded.kind, enabled=excluded.enabled,
                   label=excluded.label, configuration_json=excluded.configuration_json, credential_ref=excluded.credential_ref,
                   status=excluded.status, updated_at=excluded.updated_at""",
                (tenant_id, key, kind, int(enabled), label.strip(), json.dumps(configuration), credential_ref.strip(), status, self._now()),
            )
            conn.commit()
            return [item for item in self.configuration(tenant_id)["connections"] if item["connection_key"] == key][0]
        finally:
            conn.close()

    def invite_user(self, tenant_id: str, email: str, name: str, role: str, departments: list[str]) -> dict[str, Any]:
        if "@" not in email or len(email) > 254 or not name.strip() or role not in {"employee", "manager", "dept_head", "admin"}:
            raise TenantAdminError("A valid name, email, and supported role are required")
        now, invite_id = self._now(), f"inv_{uuid.uuid4().hex[:12]}"
        conn = self._connect()
        try:
            conn.execute("INSERT INTO tenant_invitations VALUES (?,?,?,?,?,?,?,?)", (invite_id, tenant_id, email.strip().lower(), name.strip(), role, json.dumps(departments), "pending", now))
            conn.commit()
            return {"id": invite_id, "email": email.strip().lower(), "name": name.strip(), "role": role, "departments": departments, "status": "pending", "created_at": now}
        except sqlite3.IntegrityError as error:
            raise TenantAdminError("An invitation already exists for this email") from error
        finally:
            conn.close()

    def list_invitations(self, tenant_id: str) -> list[dict[str, Any]]:
        conn = self._connect()
        try:
            return [{**dict(row), "departments": json.loads(row["departments_json"])} for row in conn.execute("SELECT * FROM tenant_invitations WHERE tenant_id=? ORDER BY created_at DESC", (tenant_id,))]
        finally:
            conn.close()


def get_tenant_admin_store() -> TenantAdminStore:
    return TenantAdminStore()
