"""Persisted organization playbooks and task-run state machine.

This is deliberately deterministic: a playbook declares its steps, risk tier,
and verification requirements.  The engine owns state transitions so an agent
or UI client cannot mark work complete by editing a status field.
"""
from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEPARTMENTS: dict[str, dict[str, Any]] = {
    "hr": {"name": "People Ops", "lead": "People Operations Lead", "agents": ["Onboarding", "Leave & PTO", "Policy & Docs", "Compliance Calendar"], "data_domains": ["HRIS", "employee records", "people policies"]},
    "finance": {"name": "Finance", "lead": "Finance Lead", "agents": ["Close Operations", "Accounts Payable", "Planning & Analysis", "Verifier"], "data_domains": ["ERP", "accounting", "expenses"]},
    "legal": {"name": "Legal", "lead": "Legal Operations Lead", "agents": ["Contract Intake", "Obligations", "Policy Review", "Verifier"], "data_domains": ["contracts", "legal policies", "e-sign"]},
    "sales": {"name": "Sales", "lead": "Revenue Lead", "agents": ["Lead Routing", "Pipeline Operations", "Deal Desk", "Verifier"], "data_domains": ["CRM", "pricing", "accounts"]},
    "marketing": {"name": "Marketing", "lead": "Marketing Operations Lead", "agents": ["Campaign Operations", "Content", "Analytics", "Verifier"], "data_domains": ["campaigns", "analytics", "brand assets"]},
    "ops": {"name": "Operations", "lead": "Operations Lead", "agents": ["Process Operations", "Incident Coordination", "SLA Monitor", "Verifier"], "data_domains": ["SOPs", "tickets", "operational KPIs"]},
    "it": {"name": "IT", "lead": "IT Operations Lead", "agents": ["Access Management", "Asset Operations", "Incident Triage", "Verifier"], "data_domains": ["identity", "assets", "service desk"]},
    "procurement": {"name": "Procurement", "lead": "Procurement Lead", "agents": ["Purchase Intake", "Vendor Operations", "Renewals", "Verifier"], "data_domains": ["vendors", "purchase orders", "contracts"]},
    "rd": {"name": "R&D / Product", "lead": "Product Operations Lead", "agents": ["Research Synthesis", "Delivery Operations", "Release Readiness", "Verifier"], "data_domains": ["roadmap", "research", "engineering delivery"]},
    "customer_success": {"name": "Customer Success", "lead": "Customer Success Lead", "agents": ["Account Health", "Onboarding", "Renewals", "Verifier"], "data_domains": ["CRM", "support", "product usage"]},
}


PLAYBOOKS: dict[str, dict[str, Any]] = {
    "onboarding": {
        "department": "hr",
        "name": "New hire onboarding",
        "description": "Prepare a new starter without losing the founder in operational work.",
        "trigger_types": ["message", "hiring_sheet"],
        "steps": [
            ("collect-details", "Collect employment details", "HR Lead", "T0"),
            ("prepare-offer", "Prepare offer and contract package", "Policy & Docs", "T2"),
            ("prepare-day-one", "Build day-one schedule", "Onboarding", "T0"),
            ("send-welcome", "Send welcome and document request", "Onboarding", "T1"),
            ("create-checklist", "Create access and equipment checklist", "Onboarding", "T0"),
        ],
    },
    "leave": {
        "department": "hr",
        "name": "Leave and PTO",
        "description": "Check policy, record leave, update the calendar, and notify the manager.",
        "trigger_types": ["message"],
        "steps": [
            ("check-policy", "Check leave policy and balance", "Leave & PTO", "T0"),
            ("record-leave", "Record approved leave", "Leave & PTO", "T0"),
            ("update-calendar", "Update team calendar", "Leave & PTO", "T0"),
            ("notify-manager", "Notify the reporting manager", "Leave & PTO", "T1"),
        ],
    },
    "compliance": {
        "department": "hr",
        "name": "People compliance calendar",
        "description": "Prepare renewal and compliance work before it becomes a deadline.",
        "trigger_types": ["schedule"],
        "steps": [
            ("review-deadline", "Review deadline and required evidence", "Compliance Calendar", "T0"),
            ("prepare-draft", "Prepare document or filing draft", "Policy & Docs", "T0"),
            ("request-signature", "Request the required signature", "Compliance Calendar", "T2"),
            ("log-deadline", "Record completion and next review date", "Compliance Calendar", "T0"),
        ],
    },
    "financial-close": {
        "department": "finance",
        "name": "Monthly financial close",
        "description": "Coordinate close evidence, variance review, and finance leadership sign-off.",
        "trigger_types": ["schedule", "erp_event"],
        "steps": [
            ("collect-ledger", "Collect ledger and close checklist evidence", "Close Operations", "T0"),
            ("review-variance", "Prepare material variance review", "Planning & Analysis", "T0"),
            ("prepare-close-pack", "Prepare close pack", "Close Operations", "T1"),
            ("approve-close", "Approve material close adjustments", "Finance Lead", "T2"),
        ],
    },
    "contract-review": {
        "department": "legal",
        "name": "Contract intake and review",
        "description": "Classify a contract, prepare a review package, and track resulting obligations.",
        "trigger_types": ["document", "message"],
        "steps": [
            ("classify-contract", "Classify contract and required review path", "Contract Intake", "T0"),
            ("extract-obligations", "Extract obligations and renewal terms", "Obligations", "T0"),
            ("prepare-redlines", "Prepare review package and redline summary", "Policy Review", "T1"),
            ("accept-terms", "Accept material contractual terms", "Legal Operations Lead", "T2"),
        ],
    },
    "lead-qualification": {
        "department": "sales",
        "name": "Lead qualification and routing",
        "description": "Validate inbound data, qualify the lead, route ownership, and prepare the first response.",
        "trigger_types": ["crm_event", "message", "form"],
        "steps": [
            ("validate-lead", "Validate lead and account data", "Lead Routing", "T0"),
            ("score-lead", "Score fit and urgency", "Pipeline Operations", "T0"),
            ("assign-owner", "Assign territory owner", "Lead Routing", "T0"),
            ("send-response", "Send the approved first response", "Deal Desk", "T1"),
        ],
    },
    "campaign-launch": {
        "department": "marketing",
        "name": "Campaign launch operations",
        "description": "Coordinate approved campaign assets, channel setup, measurement, and launch evidence.",
        "trigger_types": ["schedule", "message"],
        "steps": [
            ("validate-brief", "Validate campaign brief and audience", "Campaign Operations", "T0"),
            ("prepare-assets", "Prepare approved channel assets", "Content", "T0"),
            ("configure-measurement", "Configure tracking and measurement", "Analytics", "T0"),
            ("publish-campaign", "Publish approved campaign", "Campaign Operations", "T1"),
        ],
    },
    "operations-incident": {
        "department": "ops",
        "name": "Operational incident coordination",
        "description": "Coordinate response, evidence, ownership, and closure for an operational incident.",
        "trigger_types": ["ticket", "monitor", "message"],
        "steps": [
            ("classify-incident", "Classify impact and response level", "Incident Coordination", "T0"),
            ("assign-owners", "Assign operational owners and SLA", "Process Operations", "T0"),
            ("publish-update", "Publish stakeholder status update", "Incident Coordination", "T1"),
            ("close-incident", "Approve incident closure and follow-up", "Operations Lead", "T2"),
        ],
    },
    "access-request": {
        "department": "it",
        "name": "Access request fulfillment",
        "description": "Validate an access request, apply the least-privilege policy, and record evidence.",
        "trigger_types": ["ticket", "onboarding_event"],
        "steps": [
            ("validate-request", "Validate requester and access policy", "Access Management", "T0"),
            ("prepare-access", "Prepare least-privilege access change", "Access Management", "T1"),
            ("approve-privileged", "Approve privileged access", "IT Operations Lead", "T2"),
            ("record-access", "Record access evidence and review date", "Asset Operations", "T0"),
        ],
    },
    "purchase-request": {
        "department": "procurement",
        "name": "Purchase request and vendor review",
        "description": "Validate a request, assess vendor evidence, and coordinate the approved purchase path.",
        "trigger_types": ["form", "message", "contract_renewal"],
        "steps": [
            ("validate-request", "Validate budget owner and purchase request", "Purchase Intake", "T0"),
            ("review-vendor", "Review vendor evidence and renewal terms", "Vendor Operations", "T0"),
            ("prepare-order", "Prepare purchase order package", "Purchase Intake", "T1"),
            ("approve-spend", "Approve consequential spend", "Procurement Lead", "T2"),
        ],
    },
    "release-readiness": {
        "department": "rd",
        "name": "Release readiness review",
        "description": "Assemble delivery evidence, validate release readiness, and coordinate the go/no-go decision.",
        "trigger_types": ["deployment", "schedule"],
        "steps": [
            ("collect-release-evidence", "Collect release, test, and rollback evidence", "Release Readiness", "T0"),
            ("review-quality", "Review quality and known-risk summary", "Delivery Operations", "T0"),
            ("prepare-release-notes", "Prepare release notes and support handoff", "Research Synthesis", "T1"),
            ("approve-release", "Approve material release decision", "Product Operations Lead", "T2"),
        ],
    },
    "account-health-review": {
        "department": "customer_success",
        "name": "Customer account health review",
        "description": "Assess account health, prepare outreach, and escalate material retention risk.",
        "trigger_types": ["schedule", "usage_event", "support_event"],
        "steps": [
            ("calculate-health", "Calculate account health evidence", "Account Health", "T0"),
            ("prepare-plan", "Prepare adoption or recovery plan", "Customer Success", "T0"),
            ("send-outreach", "Send customer outreach", "Onboarding", "T1"),
            ("approve-commercial-action", "Approve material commercial concession", "Customer Success Lead", "T2"),
        ],
    },
}

FINAL_STATUSES = {"done", "escalated", "failed"}
PRIVILEGED_ROLES = {"admin", "ceo", "manager", "dept_head", "division_head", "c_suite"}
FOUNDER_ROLES = {"admin", "ceo"}


class PeopleOpsError(ValueError):
    """A safe, user-facing workflow error."""


class PeopleOpsStore:
    def __init__(self, db_path: str | None = None):
        raw_path = db_path or os.getenv("RAPID_PEOPLE_OPS_DB_PATH", "data/db/people_ops.db")
        self.db_path = Path(raw_path)
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
                CREATE TABLE IF NOT EXISTS task_runs (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    playbook_key TEXT NOT NULL,
                    subject_name TEXT NOT NULL,
                    subject_email TEXT NOT NULL DEFAULT '',
                    details_json TEXT NOT NULL DEFAULT '{}',
                    due_date TEXT,
                    status TEXT NOT NULL,
                    execution_mode TEXT NOT NULL,
                    created_by TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    completed_at TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_people_ops_runs_tenant_status
                    ON task_runs(tenant_id, status, updated_at DESC);
                CREATE TABLE IF NOT EXISTS task_steps (
                    id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    tenant_id TEXT NOT NULL,
                    sequence INTEGER NOT NULL,
                    step_key TEXT NOT NULL,
                    label TEXT NOT NULL,
                    owner TEXT NOT NULL,
                    risk_tier TEXT NOT NULL,
                    status TEXT NOT NULL,
                    evidence_json TEXT NOT NULL DEFAULT '[]',
                    completed_at TEXT,
                    UNIQUE(run_id, sequence)
                );
                CREATE TABLE IF NOT EXISTS task_events (
                    id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    tenant_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_people_ops_events_run
                    ON task_events(run_id, created_at ASC);
                CREATE TABLE IF NOT EXISTS escalations (
                    id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL UNIQUE,
                    tenant_id TEXT NOT NULL,
                    step_id TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    status TEXT NOT NULL,
                    resolved_by TEXT,
                    resolution TEXT,
                    created_at TEXT NOT NULL,
                    resolved_at TEXT
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
    def _loads(value: str | None, fallback: Any) -> Any:
        try:
            return json.loads(value or "")
        except (TypeError, json.JSONDecodeError):
            return fallback

    def _event(self, conn: sqlite3.Connection, run_id: str, tenant_id: str, event_type: str, actor: str, payload: dict) -> None:
        conn.execute(
            "INSERT INTO task_events (id, run_id, tenant_id, event_type, actor, payload_json, created_at) VALUES (?,?,?,?,?,?,?)",
            (str(uuid.uuid4()), run_id, tenant_id, event_type, actor, json.dumps(payload), self._now()),
        )

    def list_playbooks(self) -> list[dict]:
        return [
            {
                "key": key,
                "department": value["department"],
                "department_name": DEPARTMENTS[value["department"]]["name"],
                "name": value["name"],
                "description": value["description"],
                "trigger_types": value["trigger_types"],
                "step_count": len(value["steps"]),
                "autonomy": "Verified autonomy with escalation gates",
            }
            for key, value in PLAYBOOKS.items()
        ]

    def create_run(self, tenant_id: str, created_by: str, playbook_key: str, subject_name: str,
                   subject_email: str = "", due_date: str | None = None, details: dict | None = None,
                   execution_mode: str = "sandbox") -> dict:
        if playbook_key not in PLAYBOOKS:
            raise PeopleOpsError("Unknown People Ops playbook")
        if not subject_name.strip():
            raise PeopleOpsError("A person or compliance item is required")
        if execution_mode != "sandbox":
            raise PeopleOpsError("Live connector execution is not configured for this deployment")

        now = self._now()
        run_id = f"run_{uuid.uuid4().hex[:12]}"
        conn = self._connect()
        try:
            conn.execute("BEGIN")
            conn.execute(
                """INSERT INTO task_runs
                   (id, tenant_id, playbook_key, subject_name, subject_email, details_json, due_date,
                    status, execution_mode, created_by, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (run_id, tenant_id, playbook_key, subject_name.strip(), subject_email.strip(),
                 json.dumps(details or {}), due_date, "planned", execution_mode, created_by, now, now),
            )
            for sequence, (step_key, label, owner, risk_tier) in enumerate(PLAYBOOKS[playbook_key]["steps"], start=1):
                conn.execute(
                    """INSERT INTO task_steps
                       (id, run_id, tenant_id, sequence, step_key, label, owner, risk_tier, status)
                       VALUES (?,?,?,?,?,?,?,?,?)""",
                    (f"step_{uuid.uuid4().hex[:12]}", run_id, tenant_id, sequence, step_key, label, owner, risk_tier, "pending"),
                )
            self._event(conn, run_id, tenant_id, "run.created", created_by, {"playbook": playbook_key, "mode": execution_mode})
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
        return self.get_run(tenant_id, run_id)

    def _get_run_row(self, conn: sqlite3.Connection, tenant_id: str, run_id: str) -> sqlite3.Row:
        row = conn.execute("SELECT * FROM task_runs WHERE id=? AND tenant_id=?", (run_id, tenant_id)).fetchone()
        if not row:
            raise PeopleOpsError("Task run not found")
        return row

    def _serialize(self, conn: sqlite3.Connection, run: sqlite3.Row) -> dict:
        steps = [dict(row) for row in conn.execute("SELECT * FROM task_steps WHERE run_id=? AND tenant_id=? ORDER BY sequence", (run["id"], run["tenant_id"])).fetchall()]
        for step in steps:
            step["evidence"] = self._loads(step.pop("evidence_json", "[]"), [])
        events = [dict(row) for row in conn.execute("SELECT * FROM task_events WHERE run_id=? AND tenant_id=? ORDER BY created_at", (run["id"], run["tenant_id"])).fetchall()]
        for event in events:
            event["payload"] = self._loads(event.pop("payload_json", "{}"), {})
        escalation = conn.execute("SELECT * FROM escalations WHERE run_id=? AND tenant_id=?", (run["id"], run["tenant_id"])).fetchone()
        data = dict(run)
        data["details"] = self._loads(data.pop("details_json", "{}"), {})
        data["steps"] = steps
        data["events"] = events
        data["escalation"] = dict(escalation) if escalation else None
        data["playbook"] = {"key": run["playbook_key"], **PLAYBOOKS[run["playbook_key"]]}
        data["progress"] = {"complete": len([s for s in steps if s["status"] == "complete"]), "total": len(steps)}
        return data

    def get_run(self, tenant_id: str, run_id: str) -> dict:
        conn = self._connect()
        try:
            return self._serialize(conn, self._get_run_row(conn, tenant_id, run_id))
        finally:
            conn.close()

    def list_runs(self, tenant_id: str, status: str | None = None, department: str | None = None, limit: int = 100) -> list[dict]:
        conn = self._connect()
        try:
            query = "SELECT * FROM task_runs WHERE tenant_id=?"
            args: list[Any] = [tenant_id]
            if status:
                query += " AND status=?"
                args.append(status)
            query += " ORDER BY updated_at DESC LIMIT ?"
            args.append(limit)
            runs = [self._serialize(conn, row) for row in conn.execute(query, args).fetchall()]
            return [run for run in runs if department is None or run["playbook"]["department"] == department]
        finally:
            conn.close()

    def advance_to_gate(self, tenant_id: str, run_id: str, actor: str) -> dict:
        """Execute all safe steps, stopping at a T2 escalation or verifier gate."""
        conn = self._connect()
        try:
            conn.execute("BEGIN")
            run = self._get_run_row(conn, tenant_id, run_id)
            if run["status"] in FINAL_STATUSES:
                raise PeopleOpsError(f"This task run is already {run['status']}")
            if run["status"] == "verifying":
                raise PeopleOpsError("This run is waiting for independent verification")
            if run["status"] == "planned":
                conn.execute("UPDATE task_runs SET status='executing', updated_at=? WHERE id=? AND tenant_id=?", (self._now(), run_id, tenant_id))
                self._event(conn, run_id, tenant_id, "run.executing", actor, {})

            while True:
                step = conn.execute(
                    "SELECT * FROM task_steps WHERE run_id=? AND tenant_id=? AND status='pending' ORDER BY sequence LIMIT 1",
                    (run_id, tenant_id),
                ).fetchone()
                if not step:
                    conn.execute("UPDATE task_runs SET status='verifying', updated_at=? WHERE id=? AND tenant_id=?", (self._now(), run_id, tenant_id))
                    self._event(conn, run_id, tenant_id, "run.verifying", "Verifier", {"check": "required evidence present"})
                    break
                if step["risk_tier"] == "T2":
                    escalation_id = f"esc_{uuid.uuid4().hex[:12]}"
                    conn.execute(
                        """INSERT OR REPLACE INTO escalations
                           (id, run_id, tenant_id, step_id, reason, status, created_at)
                           VALUES (?,?,?,?,?,?,?)""",
                        (escalation_id, run_id, tenant_id, step["id"], f"{step['label']} is a consequential action ({step['risk_tier']}).", "open", self._now()),
                    )
                    conn.execute("UPDATE task_runs SET status='escalated', updated_at=? WHERE id=? AND tenant_id=?", (self._now(), run_id, tenant_id))
                    self._event(conn, run_id, tenant_id, "run.escalated", "Policy Engine", {"step": step["step_key"], "risk_tier": step["risk_tier"]})
                    break
                evidence = [{
                    "type": "sandbox_receipt",
                    "reference": f"sandbox://{run['playbook_key']}/{run_id}/{step['step_key']}",
                    "verified_by": "execution-adapter",
                    "recorded_at": self._now(),
                }]
                conn.execute("UPDATE task_steps SET status='complete', evidence_json=?, completed_at=? WHERE id=? AND tenant_id=?", (json.dumps(evidence), self._now(), step["id"], tenant_id))
                self._event(conn, run_id, tenant_id, "step.executed", step["owner"], {"step": step["step_key"], "mode": "sandbox"})
                conn.execute("UPDATE task_runs SET updated_at=? WHERE id=? AND tenant_id=?", (self._now(), run_id, tenant_id))
            conn.commit()
            return self._serialize(conn, self._get_run_row(conn, tenant_id, run_id))
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def resolve_escalation(self, tenant_id: str, run_id: str, actor: str, decision: str, note: str = "") -> dict:
        if decision not in {"approve", "reject"}:
            raise PeopleOpsError("Decision must be approve or reject")
        conn = self._connect()
        try:
            conn.execute("BEGIN")
            run = self._get_run_row(conn, tenant_id, run_id)
            esc = conn.execute("SELECT * FROM escalations WHERE run_id=? AND tenant_id=? AND status='open'", (run_id, tenant_id)).fetchone()
            if not esc or run["status"] != "escalated":
                raise PeopleOpsError("There is no open escalation for this task run")
            if decision == "reject":
                conn.execute("UPDATE task_runs SET status='failed', updated_at=? WHERE id=? AND tenant_id=?", (self._now(), run_id, tenant_id))
            else:
                step = conn.execute("SELECT * FROM task_steps WHERE id=? AND tenant_id=?", (esc["step_id"], tenant_id)).fetchone()
                evidence = [{"type": "founder_approval", "reference": esc["id"], "approved_by": actor, "note": note, "recorded_at": self._now()}]
                conn.execute("UPDATE task_steps SET status='complete', evidence_json=?, completed_at=? WHERE id=? AND tenant_id=?", (json.dumps(evidence), self._now(), step["id"], tenant_id))
                conn.execute("UPDATE task_runs SET status='executing', updated_at=? WHERE id=? AND tenant_id=?", (self._now(), run_id, tenant_id))
            conn.execute("UPDATE escalations SET status=?, resolved_by=?, resolution=?, resolved_at=? WHERE id=? AND tenant_id=?", ("approved" if decision == "approve" else "rejected", actor, note, self._now(), esc["id"], tenant_id))
            self._event(conn, run_id, tenant_id, "escalation.resolved", actor, {"decision": decision, "note": note})
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
        return self.advance_to_gate(tenant_id, run_id, actor) if decision == "approve" else self.get_run(tenant_id, run_id)

    def verify_run(self, tenant_id: str, run_id: str, actor: str = "Verifier") -> dict:
        conn = self._connect()
        try:
            conn.execute("BEGIN")
            run = self._get_run_row(conn, tenant_id, run_id)
            if run["status"] != "verifying":
                raise PeopleOpsError("A run must reach the verifier gate before it can complete")
            missing = conn.execute("SELECT label FROM task_steps WHERE run_id=? AND tenant_id=? AND (status != 'complete' OR evidence_json = '[]')", (run_id, tenant_id)).fetchall()
            if missing:
                raise PeopleOpsError("Verification failed: one or more steps have no evidence")
            now = self._now()
            conn.execute("UPDATE task_runs SET status='done', updated_at=?, completed_at=? WHERE id=? AND tenant_id=?", (now, now, run_id, tenant_id))
            self._event(conn, run_id, tenant_id, "run.verified", actor, {"result": "passed", "method": "independent evidence check"})
            conn.commit()
            return self._serialize(conn, self._get_run_row(conn, tenant_id, run_id))
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def handoff_run(self, tenant_id: str, source_run_id: str, created_by: str, target_playbook_key: str,
                    subject_name: str, subject_email: str = "", details: dict | None = None) -> dict:
        """Create a linked downstream run after its source has independently verified."""
        if target_playbook_key not in PLAYBOOKS:
            raise PeopleOpsError("Unknown organization playbook")

        conn = self._connect()
        try:
            conn.execute("BEGIN")
            source = self._get_run_row(conn, tenant_id, source_run_id)
            if source["status"] != "done":
                raise PeopleOpsError("A run must be independently verified before it can be handed off")
            source_department = PLAYBOOKS[source["playbook_key"]]["department"]
            target_department = PLAYBOOKS[target_playbook_key]["department"]
            if source_department == target_department:
                raise PeopleOpsError("A handoff must target a different department")
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

        handoff_details = dict(details or {})
        handoff_details["handoff"] = {
            "source_run_id": source_run_id,
            "source_playbook": source["playbook_key"],
            "source_department": source_department,
            "target_department": target_department,
        }
        target = self.create_run(
            tenant_id=tenant_id,
            created_by=created_by,
            playbook_key=target_playbook_key,
            subject_name=subject_name,
            subject_email=subject_email,
            details=handoff_details,
        )

        conn = self._connect()
        try:
            conn.execute("BEGIN")
            self._event(conn, source_run_id, tenant_id, "run.handed_off", created_by, {
                "target_run_id": target["id"],
                "target_playbook": target_playbook_key,
                "target_department": target_department,
            })
            self._event(conn, target["id"], tenant_id, "run.received_handoff", created_by, {
                "source_run_id": source_run_id,
                "source_playbook": source["playbook_key"],
                "source_department": source_department,
            })
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
        return self.get_run(tenant_id, target["id"])

    def dashboard(self, tenant_id: str) -> dict:
        runs = self.list_runs(tenant_id, limit=30)
        statuses = {status: sum(run["status"] == status for run in runs) for status in ("planned", "executing", "verifying", "done", "escalated", "failed")}
        return {
            "runs": runs,
            "stats": {"total": len(runs), **statuses, "autonomous_completion_rate": self._completion_rate(runs)},
            "escalations": [run for run in runs if run["status"] == "escalated"],
            "departments": self.department_summary(runs),
        }

    def department_summary(self, runs: list[dict]) -> list[dict]:
        return [
            {
                "key": key,
                **definition,
                "active_runs": sum(run["playbook"]["department"] == key and run["status"] not in {"done", "failed"} for run in runs),
                "completed_runs": sum(run["playbook"]["department"] == key and run["status"] == "done" for run in runs),
                "escalations": sum(run["playbook"]["department"] == key and run["status"] == "escalated" for run in runs),
            }
            for key, definition in DEPARTMENTS.items()
        ]

    def department_report(self, tenant_id: str, department: str) -> dict:
        if department not in DEPARTMENTS:
            raise PeopleOpsError("Unknown department")
        runs = self.list_runs(tenant_id, department=department)
        completed = [run for run in runs if run["status"] == "done"]
        evidence_total = sum(len(step["evidence"]) for run in runs for step in run["steps"])
        return {
            "department": {"key": department, **DEPARTMENTS[department]},
            "generated_at": self._now(),
            "metrics": {
                "total_runs": len(runs),
                "active_runs": sum(run["status"] not in {"done", "failed"} for run in runs),
                "completed_runs": len(completed),
                "open_escalations": sum(run["status"] == "escalated" for run in runs),
                "verification_rate": self._completion_rate(runs),
                "evidence_records": evidence_total,
            },
            "recent_runs": runs[:10],
            "sources": {
                "structured": DEPARTMENTS[department]["data_domains"],
                "unstructured": ["department policies", "approved documents", "run evidence"],
                "execution_mode": "sandbox",
            },
        }

    @staticmethod
    def _completion_rate(runs: list[dict]) -> int:
        settled = [run for run in runs if run["status"] in {"done", "failed"}]
        if not settled:
            return 0
        return round((sum(run["status"] == "done" for run in settled) / len(settled)) * 100)


def get_people_ops_store() -> PeopleOpsStore:
    return PeopleOpsStore()
