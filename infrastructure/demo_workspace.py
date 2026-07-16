"""Synthetic, tenant-scoped organization workspace used for product evaluation."""
from __future__ import annotations

import json
import os
import re
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from infrastructure.people_ops_store import DEPARTMENTS


class WorkspaceError(ValueError):
    """Safe workspace error exposed by the API."""


class DemoWorkspaceStore:
    def __init__(self, db_path: str | None = None):
        self.db_path = Path(db_path or os.getenv("RAPID_WORKSPACE_DB_PATH", "data/db/workspace.db"))
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
                CREATE TABLE IF NOT EXISTS workspace_organizations (
                    tenant_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    industry TEXT NOT NULL,
                    headquarters TEXT NOT NULL,
                    employee_count INTEGER NOT NULL,
                    initialized_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS workspace_meetings (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    meeting_type TEXT NOT NULL,
                    department TEXT NOT NULL DEFAULT '',
                    starts_at TEXT NOT NULL,
                    duration_minutes INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    facilitator TEXT NOT NULL,
                    attendees_json TEXT NOT NULL DEFAULT '[]',
                    agenda_json TEXT NOT NULL DEFAULT '[]',
                    notes TEXT NOT NULL DEFAULT '',
                    decisions_json TEXT NOT NULL DEFAULT '[]',
                    recurrence TEXT NOT NULL DEFAULT 'none',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_workspace_meetings_scope
                    ON workspace_meetings(tenant_id, starts_at);
                CREATE TABLE IF NOT EXISTS workspace_actions (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    meeting_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    owner TEXT NOT NULL,
                    department TEXT NOT NULL,
                    due_date TEXT NOT NULL,
                    status TEXT NOT NULL,
                    priority TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_workspace_actions_scope
                    ON workspace_actions(tenant_id, status, due_date);
                CREATE TABLE IF NOT EXISTS workspace_entities (
                    id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, entity_type TEXT NOT NULL,
                    department TEXT NOT NULL, name TEXT NOT NULL, data_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_workspace_entities_scope
                    ON workspace_entities(tenant_id, entity_type, department);
                CREATE TABLE IF NOT EXISTS workspace_notifications (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    message TEXT NOT NULL,
                    category TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    source_id TEXT NOT NULL DEFAULT '',
                    is_read INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_workspace_notifications_scope
                    ON workspace_notifications(tenant_id, is_read, created_at DESC);
                """
            )
            columns = {row[1] for row in conn.execute("PRAGMA table_info(workspace_meetings)").fetchall()}
            if "recurrence" not in columns:
                conn.execute("ALTER TABLE workspace_meetings ADD COLUMN recurrence TEXT NOT NULL DEFAULT 'none'")
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _stamp(value: datetime) -> str:
        return value.isoformat()

    @staticmethod
    def _loads(value: str | None) -> list[Any]:
        try:
            return json.loads(value or "[]")
        except json.JSONDecodeError:
            return []

    def ensure_workspace(self, tenant_id: str) -> None:
        conn = self._connect()
        try:
            if conn.execute("SELECT 1 FROM workspace_organizations WHERE tenant_id=?", (tenant_id,)).fetchone():
                return
            now = self._now()
            conn.execute(
                "INSERT INTO workspace_organizations VALUES (?,?,?,?,?,?)",
                (tenant_id, "Northstar Labs", "B2B software", "New York, United States", 184, self._stamp(now)),
            )
            meetings = [
                ("Executive operating review", "Operating review", "", now + timedelta(hours=2), 60, "scheduled", "Maya Chen", ["Maya Chen", "Arjun Rao", "Sofia Martinez", "Elena Brooks"], ["Review operating metrics", "Resolve cross-team risks", "Confirm this week's decisions"], "", [], "weekly"),
                ("Revenue and pipeline review", "Department review", "sales", now + timedelta(hours=4), 45, "scheduled", "Arjun Rao", ["Arjun Rao", "Hannah Kim", "Derek Long"], ["Inspect enterprise pipeline", "Confirm territory coverage", "Review expansion risk"], "", [], "weekly"),
                ("Release readiness", "Delivery review", "rd", now - timedelta(days=1, hours=3), 50, "completed", "Sofia Martinez", ["Sofia Martinez", "Leo Grant", "Nina Patel", "Avery Collins"], ["Review release evidence", "Validate support readiness", "Confirm rollback owner"], "The release is ready after support confirms the migration guidance.", ["Release v2.8 approved for Thursday", "Customer Success owns migration communications"], "none"),
                ("People capacity review", "Department review", "hr", now + timedelta(days=1, hours=3), 30, "scheduled", "Elena Brooks", ["Elena Brooks", "Jordan Bell"], ["Review hiring plan", "Check manager workload", "Confirm onboarding coverage"], "", [], "monthly"),
            ]
            meeting_ids: list[str] = []
            for title, kind, department, starts_at, duration, status, facilitator, attendees, agenda, notes, decisions, recurrence in meetings:
                meeting_id = f"mtg_{uuid.uuid4().hex[:12]}"
                meeting_ids.append(meeting_id)
                conn.execute(
                    """INSERT INTO workspace_meetings
                       (id, tenant_id, title, meeting_type, department, starts_at, duration_minutes, status, facilitator,
                        attendees_json, agenda_json, notes, decisions_json, recurrence, created_at, updated_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (meeting_id, tenant_id, title, kind, department, self._stamp(starts_at), duration, status, facilitator,
                     json.dumps(attendees), json.dumps(agenda), notes, json.dumps(decisions), recurrence, self._stamp(now), self._stamp(now)),
                )
            actions = [
                (meeting_ids[0], "Confirm renewal recovery plan for Atlas Group", "Hannah Kim", "customer_success", now + timedelta(days=2), "open", "high"),
                (meeting_ids[0], "Validate Q3 hiring capacity against plan", "Elena Brooks", "hr", now + timedelta(days=3), "open", "medium"),
                (meeting_ids[2], "Publish migration guidance for v2.8", "Avery Collins", "customer_success", now + timedelta(days=1), "in_progress", "high"),
                (meeting_ids[1], "Reconcile strategic account ownership", "Derek Long", "sales", now + timedelta(days=4), "open", "medium"),
            ]
            for meeting_id, title, owner, department, due, status, priority in actions:
                conn.execute(
                    "INSERT INTO workspace_actions VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (f"act_{uuid.uuid4().hex[:12]}", tenant_id, meeting_id, title, owner, department, self._stamp(due), status, priority, self._stamp(now), self._stamp(now)),
                )
            entities = [
                ("employee", "hr", "Maya Chen", {"title": "Chief Executive Officer", "location": "New York", "manager": "Board"}),
                ("employee", "hr", "Arjun Rao", {"title": "Revenue Lead", "location": "New York", "manager": "Maya Chen"}),
                ("employee", "hr", "Elena Brooks", {"title": "People Operations Lead", "location": "Boston", "manager": "Maya Chen"}),
                ("employee", "finance", "Marcus Lee", {"title": "Finance Lead", "location": "New York", "manager": "Maya Chen"}),
                ("employee", "legal", "Priya Shah", {"title": "Legal Operations Lead", "location": "Washington, DC", "manager": "Maya Chen"}),
                ("employee", "sales", "Hannah Kim", {"title": "Enterprise Sales Manager", "location": "Chicago", "manager": "Arjun Rao"}),
                ("employee", "marketing", "Camille Foster", {"title": "Marketing Lead", "location": "Austin", "manager": "Maya Chen"}),
                ("employee", "ops", "Jordan Bell", {"title": "Operations Lead", "location": "New York", "manager": "Maya Chen"}),
                ("employee", "it", "Nina Patel", {"title": "IT and Security Lead", "location": "Seattle", "manager": "Maya Chen"}),
                ("employee", "procurement", "Owen Wright", {"title": "Procurement Manager", "location": "Denver", "manager": "Marcus Lee"}),
                ("employee", "rd", "Sofia Martinez", {"title": "Product and R&D Lead", "location": "San Francisco", "manager": "Maya Chen"}),
                ("employee", "customer_success", "Avery Collins", {"title": "Customer Success Lead", "location": "Atlanta", "manager": "Arjun Rao"}),
                ("customer", "customer_success", "Atlas Group", {"segment": "Enterprise", "renewal": "2026-09-30", "health": "at_risk", "arr": 240000}),
                ("customer", "customer_success", "Harbor Health", {"segment": "Mid-market", "renewal": "2027-01-15", "health": "healthy", "arr": 98000}),
                ("customer", "customer_success", "Beacon Commerce", {"segment": "Enterprise", "renewal": "2026-12-12", "health": "healthy", "arr": 175000}),
                ("lead", "sales", "Asteron Systems", {"stage": "Qualified", "owner": "Hannah Kim", "value": 180000}),
                ("deal", "sales", "Beacon Commerce expansion", {"stage": "Proposal", "owner": "Derek Long", "value": 125000}),
                ("deal", "sales", "Asteron platform agreement", {"stage": "Discovery", "owner": "Hannah Kim", "value": 180000}),
                ("invoice", "finance", "Atlas Group July invoice", {"amount": 20000, "status": "sent", "due_date": "2026-07-31"}),
                ("vendor", "procurement", "Clearframe Security", {"category": "Security", "renewal": "2027-03-01", "status": "approved"}),
                ("contract", "legal", "Atlas Group renewal agreement", {"status": "review", "renewal": "2026-09-30", "owner": "Legal Operations"}),
                ("campaign", "marketing", "Q3 Operations Intelligence", {"status": "active", "audience": "Enterprise operations", "channel": "Webinar"}),
                ("project", "rd", "Northstar v2.8", {"status": "release_ready", "owner": "Sofia Martinez", "target": "2026-07-23"}),
                ("project", "ops", "Enterprise onboarding redesign", {"status": "in_progress", "owner": "Jordan Bell", "target": "2026-08-14"}),
                ("project", "it", "Identity provider rollout", {"status": "at_risk", "owner": "Nina Patel", "target": "2026-08-01"}),
                ("ticket", "ops", "OPS-431 degraded data sync", {"priority": "high", "status": "investigating", "owner": "Incident Coordination"}),
                ("ticket", "customer_success", "CS-218 Atlas export timeout", {"priority": "medium", "status": "open", "owner": "Avery Collins"}),
                ("ticket", "it", "IT-109 SSO group mismatch", {"priority": "high", "status": "triage", "owner": "Nina Patel"}),
                ("access_request", "it", "Privileged analytics access", {"requester": "Nina Patel", "status": "approval_required", "risk": "T2"}),
            ]
            for entity_type, department, name, payload in entities:
                conn.execute("INSERT INTO workspace_entities VALUES (?,?,?,?,?,?,?)", (f"ent_{uuid.uuid4().hex[:12]}", tenant_id, entity_type, department, name, json.dumps(payload), self._stamp(now)))
            notifications = [
                ("Renewal risk needs an owner", "Atlas Group is within 90 days of renewal and remains at risk.", "customer", "urgent", "customer", "Atlas Group"),
                ("Release decision recorded", "Northstar v2.8 was approved for Thursday with a support handoff.", "decision", "info", "meeting", meeting_ids[2]),
                ("Privileged access awaiting review", "The analytics access request requires an IT approver.", "approval", "high", "access_request", "Privileged analytics access"),
                ("Data sync incident active", "OPS-431 remains under investigation by Operations.", "incident", "high", "ticket", "OPS-431 degraded data sync"),
            ]
            for title, message, category, severity, source_type, source_id in notifications:
                conn.execute(
                    "INSERT INTO workspace_notifications VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (f"ntf_{uuid.uuid4().hex[:12]}", tenant_id, title, message, category, severity, source_type, source_id, 0, self._stamp(now)),
                )
            conn.commit()
        finally:
            conn.close()

    def provision_workspace(
        self,
        *,
        tenant_id: str,
        company_name: str,
        industry: str,
        department_keys: list[str],
    ) -> None:
        """Create a tailored synthetic evaluation workspace for a new tenant."""
        self.ensure_workspace(tenant_id)
        departments = list(dict.fromkeys(key for key in department_keys if key in DEPARTMENTS))
        if not departments:
            raise WorkspaceError("At least one department is required to provision a workspace")
        conn = self._connect()
        try:
            conn.execute(
                "UPDATE workspace_organizations SET name=?, industry=?, employee_count=? WHERE tenant_id=?",
                (company_name.strip(), industry.strip() or "General business", max(2, len(departments) * 2), tenant_id),
            )
            conn.commit()
        finally:
            conn.close()

    def reset_workspace(self, tenant_id: str) -> dict[str, Any]:
        """Restore only this tenant's local evaluation data to its initial state."""
        conn = self._connect()
        try:
            conn.execute("DELETE FROM workspace_actions WHERE tenant_id=?", (tenant_id,))
            conn.execute("DELETE FROM workspace_meetings WHERE tenant_id=?", (tenant_id,))
            conn.execute("DELETE FROM workspace_entities WHERE tenant_id=?", (tenant_id,))
            conn.execute("DELETE FROM workspace_notifications WHERE tenant_id=?", (tenant_id,))
            conn.execute("DELETE FROM workspace_organizations WHERE tenant_id=?", (tenant_id,))
            conn.commit()
        finally:
            conn.close()
        self.ensure_workspace(tenant_id)
        self.ensure_knowledge(tenant_id)
        return self.overview(tenant_id)

    def ensure_knowledge(self, tenant_id: str) -> None:
        """Seed a local, department-scoped knowledge corpus for the demo tenant."""
        from infrastructure.organization_data_store import OrganizationDataError, get_organization_data_store

        store = get_organization_data_store()
        documents = {
            "hr": ("People operating policy", "Northstar hires through structured interview panels. Managers review capacity monthly and every new starter receives a documented access and equipment checklist."),
            "finance": ("Monthly close guide", "Finance reconciles the ledger by the fifth business day. Material variances require evidence, an explanation, and Finance Lead approval before the close is verified."),
            "legal": ("Contract review policy", "Legal classifies incoming agreements, extracts obligations and renewal terms, and records material contractual decisions before acceptance."),
            "sales": ("Enterprise qualification guide", "Sales qualifies enterprise leads using fit, urgency, account coverage, and confirmed next steps. Territory ownership must be recorded before the first response."),
            "marketing": ("Campaign launch standard", "Marketing validates the campaign brief, approved audience, channel assets, and measurement plan before campaign publication."),
            "ops": ("Incident coordination runbook", "Operations classifies impact, assigns an owner and SLA, publishes status updates, and creates a follow-up record before incident closure."),
            "it": ("Least privilege access standard", "IT validates a requester, applies least privilege, requires approval for privileged access, and records access review evidence."),
            "procurement": ("Vendor review standard", "Procurement checks budget ownership, vendor evidence, renewal obligations, and purchase approval before an order is issued."),
            "rd": ("Release readiness checklist", "Product and R&D collect test, rollback, release-note, and support-handoff evidence before a material release decision."),
            "customer_success": ("Account health playbook", "Customer Success uses product usage, support activity, renewal timing, and stakeholder engagement to prepare an adoption or recovery plan."),
        }
        for department, (name, content) in documents.items():
            source_name = f"Northstar {DEPARTMENTS[department]['name']} knowledge"
            try:
                source = store.register_source(tenant_id, department, source_name, "unstructured", "local_demo", "internal", "demo_seed")
                store.add_document(tenant_id, source["id"], name, content)
            except OrganizationDataError as error:
                if "already exists" not in str(error).lower():
                    raise

    def _meeting(self, row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        data["attendees"] = self._loads(data.pop("attendees_json"))
        data["agenda"] = self._loads(data.pop("agenda_json"))
        data["decisions"] = self._loads(data.pop("decisions_json"))
        return data

    def list_meetings(self, tenant_id: str, status: str | None = None, departments: set[str] | None = None) -> list[dict[str, Any]]:
        self.ensure_workspace(tenant_id)
        conn = self._connect()
        try:
            query, values = "SELECT * FROM workspace_meetings WHERE tenant_id=?", [tenant_id]
            if status:
                query += " AND status=?"
                values.append(status)
            if departments is not None:
                if not departments:
                    return []
                placeholders = ",".join("?" for _ in departments)
                query += f" AND (department='' OR department IN ({placeholders}))"
                values.extend(sorted(departments))
            query += " ORDER BY starts_at ASC"
            return [self._meeting(row) for row in conn.execute(query, values).fetchall()]
        finally:
            conn.close()

    def get_meeting(self, tenant_id: str, meeting_id: str) -> dict[str, Any]:
        self.ensure_workspace(tenant_id)
        conn = self._connect()
        try:
            row = conn.execute("SELECT * FROM workspace_meetings WHERE id=? AND tenant_id=?", (meeting_id, tenant_id)).fetchone()
            if not row:
                raise WorkspaceError("Meeting not found")
            data = self._meeting(row)
            data["actions"] = [dict(item) for item in conn.execute("SELECT * FROM workspace_actions WHERE meeting_id=? AND tenant_id=? ORDER BY due_date", (meeting_id, tenant_id)).fetchall()]
            return data
        finally:
            conn.close()

    def create_meeting(self, tenant_id: str, title: str, meeting_type: str, department: str, starts_at: str,
                       duration_minutes: int, facilitator: str, attendees: list[str], agenda: list[str],
                       recurrence: str = "none") -> dict[str, Any]:
        if not title.strip() or not facilitator.strip() or not agenda:
            raise WorkspaceError("A title, facilitator, and at least one agenda item are required")
        if department and department not in DEPARTMENTS:
            raise WorkspaceError("Unknown department")
        if duration_minutes < 15 or duration_minutes > 480:
            raise WorkspaceError("Meeting duration must be between 15 and 480 minutes")
        if recurrence not in {"none", "daily", "weekly", "biweekly", "monthly", "quarterly"}:
            raise WorkspaceError("Unsupported meeting recurrence")
        try:
            datetime.fromisoformat(starts_at.replace("Z", "+00:00"))
        except ValueError as error:
            raise WorkspaceError("Meeting start time must be a valid ISO date-time") from error
        self.ensure_workspace(tenant_id)
        meeting_id, now = f"mtg_{uuid.uuid4().hex[:12]}", self._stamp(self._now())
        conn = self._connect()
        try:
            conn.execute(
                """INSERT INTO workspace_meetings
                   (id, tenant_id, title, meeting_type, department, starts_at, duration_minutes, status, facilitator,
                    attendees_json, agenda_json, notes, decisions_json, recurrence, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (meeting_id, tenant_id, title.strip(), meeting_type.strip() or "Operating review", department, starts_at,
                 duration_minutes, "scheduled", facilitator.strip(), json.dumps([item.strip() for item in attendees if item.strip()]),
                 json.dumps([item.strip() for item in agenda if item.strip()]), "", "[]", recurrence, now, now),
            )
            conn.commit()
        finally:
            conn.close()
        return self.get_meeting(tenant_id, meeting_id)

    def update_meeting_record(self, tenant_id: str, meeting_id: str, notes: str, decisions: list[str]) -> dict[str, Any]:
        self.ensure_workspace(tenant_id)
        if len(notes) > 20_000 or any(len(item) > 1_000 for item in decisions):
            raise WorkspaceError("Meeting notes or decisions exceed the allowed length")
        conn = self._connect()
        try:
            result = conn.execute("UPDATE workspace_meetings SET notes=?, decisions_json=?, updated_at=? WHERE id=? AND tenant_id=?", (notes.strip(), json.dumps([item.strip() for item in decisions if item.strip()]), self._stamp(self._now()), meeting_id, tenant_id))
            if not result.rowcount: raise WorkspaceError("Meeting not found")
            conn.commit()
        finally:
            conn.close()
        return self.get_meeting(tenant_id, meeting_id)

    def update_meeting(self, tenant_id: str, meeting_id: str, values: dict[str, Any]) -> dict[str, Any]:
        """Update editable meeting fields while keeping the tenant boundary in the write."""
        meeting = self.get_meeting(tenant_id, meeting_id)
        allowed = {
            "title", "meeting_type", "department", "starts_at", "duration_minutes", "facilitator",
            "attendees", "agenda", "notes", "decisions", "recurrence", "status",
        }
        update = {key: value for key, value in values.items() if key in allowed and value is not None}
        if not update:
            return meeting
        merged = {**meeting, **update}
        if not str(merged["title"]).strip() or not str(merged["facilitator"]).strip() or not merged["agenda"]:
            raise WorkspaceError("A title, facilitator, and at least one agenda item are required")
        if merged["department"] and merged["department"] not in DEPARTMENTS:
            raise WorkspaceError("Unknown department")
        if merged["recurrence"] not in {"none", "daily", "weekly", "biweekly", "monthly", "quarterly"}:
            raise WorkspaceError("Unsupported meeting recurrence")
        if merged["status"] not in {"scheduled", "in_progress", "completed", "cancelled"}:
            raise WorkspaceError("Unsupported meeting status")
        if not 15 <= int(merged["duration_minutes"]) <= 480:
            raise WorkspaceError("Meeting duration must be between 15 and 480 minutes")
        try:
            datetime.fromisoformat(str(merged["starts_at"]).replace("Z", "+00:00"))
        except ValueError as error:
            raise WorkspaceError("Meeting start time must be a valid ISO date-time") from error
        conn = self._connect()
        try:
            result = conn.execute(
                """UPDATE workspace_meetings SET title=?, meeting_type=?, department=?, starts_at=?, duration_minutes=?,
                   status=?, facilitator=?, attendees_json=?, agenda_json=?, notes=?, decisions_json=?, recurrence=?, updated_at=?
                   WHERE id=? AND tenant_id=?""",
                (str(merged["title"]).strip(), str(merged["meeting_type"]).strip(), merged["department"], merged["starts_at"],
                 int(merged["duration_minutes"]), merged["status"], str(merged["facilitator"]).strip(),
                 json.dumps([str(item).strip() for item in merged["attendees"] if str(item).strip()]),
                 json.dumps([str(item).strip() for item in merged["agenda"] if str(item).strip()]), str(merged["notes"]).strip(),
                 json.dumps([str(item).strip() for item in merged["decisions"] if str(item).strip()]), merged["recurrence"],
                 self._stamp(self._now()), meeting_id, tenant_id),
            )
            if not result.rowcount:
                raise WorkspaceError("Meeting not found")
            conn.commit()
        finally:
            conn.close()
        return self.get_meeting(tenant_id, meeting_id)

    def create_meeting_action(self, tenant_id: str, meeting_id: str, title: str, owner: str, department: str, due_date: str, priority: str) -> dict[str, Any]:
        if not title.strip() or not owner.strip() or department not in DEPARTMENTS or priority not in {"low", "medium", "high"}:
            raise WorkspaceError("Action title, owner, department, and priority are required")
        self.get_meeting(tenant_id, meeting_id)
        action = {"id": f"act_{uuid.uuid4().hex[:12]}", "tenant_id": tenant_id, "meeting_id": meeting_id, "title": title.strip(), "owner": owner.strip(), "department": department, "due_date": due_date, "status": "open", "priority": priority, "created_at": self._stamp(self._now()), "updated_at": self._stamp(self._now())}
        conn = self._connect()
        try:
            conn.execute("INSERT INTO workspace_actions VALUES (?,?,?,?,?,?,?,?,?,?,?)", tuple(action.values()))
            conn.commit()
        finally:
            conn.close()
        return action

    def list_actions(self, tenant_id: str, status: str | None = None, departments: set[str] | None = None) -> list[dict[str, Any]]:
        self.ensure_workspace(tenant_id)
        conn = self._connect()
        try:
            query, values = "SELECT * FROM workspace_actions WHERE tenant_id=?", [tenant_id]
            if status:
                query += " AND status=?"
                values.append(status)
            if departments is not None:
                if not departments:
                    return []
                placeholders = ",".join("?" for _ in departments)
                query += f" AND department IN ({placeholders})"
                values.extend(sorted(departments))
            query += " ORDER BY CASE priority WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END, due_date ASC"
            return [dict(row) for row in conn.execute(query, values).fetchall()]
        finally:
            conn.close()

    def list_entities(self, tenant_id: str, entity_type: str | None = None, departments: set[str] | None = None) -> list[dict[str, Any]]:
        self.ensure_workspace(tenant_id)
        conn = self._connect()
        try:
            query, values = "SELECT * FROM workspace_entities WHERE tenant_id=?", [tenant_id]
            if entity_type:
                query += " AND entity_type=?"
                values.append(entity_type)
            if departments is not None:
                if not departments:
                    return []
                placeholders = ",".join("?" for _ in departments)
                query += f" AND department IN ({placeholders})"
                values.extend(sorted(departments))
            query += " ORDER BY entity_type, name"
            return [{**dict(row), "data": json.loads(row["data_json"])} for row in conn.execute(query, values).fetchall()]
        finally:
            conn.close()

    def update_action_status(self, tenant_id: str, action_id: str, status: str) -> dict[str, Any]:
        if status not in {"open", "in_progress", "done"}:
            raise WorkspaceError("Unsupported action status")
        self.ensure_workspace(tenant_id)
        conn = self._connect()
        try:
            result = conn.execute("UPDATE workspace_actions SET status=?, updated_at=? WHERE id=? AND tenant_id=?", (status, self._stamp(self._now()), action_id, tenant_id))
            if not result.rowcount:
                raise WorkspaceError("Action not found")
            conn.commit()
            row = conn.execute("SELECT * FROM workspace_actions WHERE id=? AND tenant_id=?", (action_id, tenant_id)).fetchone()
            return dict(row)
        finally:
            conn.close()

    def list_notifications(self, tenant_id: str, include_read: bool = False) -> list[dict[str, Any]]:
        self.ensure_workspace(tenant_id)
        conn = self._connect()
        try:
            query, values = "SELECT * FROM workspace_notifications WHERE tenant_id=?", [tenant_id]
            if not include_read:
                query += " AND is_read=0"
            query += " ORDER BY created_at DESC"
            return [{**dict(row), "is_read": bool(row["is_read"])} for row in conn.execute(query, values).fetchall()]
        finally:
            conn.close()

    def mark_notification_read(self, tenant_id: str, notification_id: str) -> dict[str, Any]:
        self.ensure_workspace(tenant_id)
        conn = self._connect()
        try:
            result = conn.execute(
                "UPDATE workspace_notifications SET is_read=1 WHERE id=? AND tenant_id=?",
                (notification_id, tenant_id),
            )
            if not result.rowcount:
                raise WorkspaceError("Notification not found")
            conn.commit()
            row = conn.execute("SELECT * FROM workspace_notifications WHERE id=? AND tenant_id=?", (notification_id, tenant_id)).fetchone()
            return {**dict(row), "is_read": bool(row["is_read"])}
        finally:
            conn.close()

    def search(self, tenant_id: str, query: str, limit: int = 30, departments: set[str] | None = None) -> dict[str, Any]:
        self.ensure_workspace(tenant_id)
        terms = [term for term in re.findall(r"[a-zA-Z0-9_-]+", query.lower()) if len(term) > 1]
        if not terms:
            raise WorkspaceError("Search needs at least one meaningful term")
        items: list[dict[str, Any]] = []
        for entity in self.list_entities(tenant_id, departments=departments):
            haystack = f"{entity['name']} {entity['entity_type']} {entity['department']} {json.dumps(entity['data'])}".lower()
            score = sum(haystack.count(term) for term in terms)
            if score:
                items.append({"id": entity["id"], "type": entity["entity_type"], "title": entity["name"], "subtitle": entity["department"], "score": score, "data": entity["data"]})
        for meeting in self.list_meetings(tenant_id, departments=departments):
            haystack = f"{meeting['title']} {meeting['meeting_type']} {meeting['department']} {meeting['notes']} {' '.join(meeting['decisions'])}".lower()
            score = sum(haystack.count(term) for term in terms)
            if score:
                items.append({"id": meeting["id"], "type": "meeting", "title": meeting["title"], "subtitle": meeting["meeting_type"], "score": score, "data": {"starts_at": meeting["starts_at"], "status": meeting["status"]}})
        for action in self.list_actions(tenant_id, departments=departments):
            haystack = f"{action['title']} {action['owner']} {action['department']} {action['status']}".lower()
            score = sum(haystack.count(term) for term in terms)
            if score:
                items.append({"id": action["id"], "type": "action", "title": action["title"], "subtitle": action["owner"], "score": score, "data": {"status": action["status"], "due_date": action["due_date"]}})
        items.sort(key=lambda item: (-item["score"], item["title"]))
        return {"query": query, "results": items[:limit], "count": min(len(items), limit), "retrieval": "tenant_scoped_workspace"}

    def overview(self, tenant_id: str, department_keys: set[str] | None = None) -> dict[str, Any]:
        self.ensure_workspace(tenant_id)
        self.ensure_knowledge(tenant_id)
        conn = self._connect()
        try:
            organization = dict(conn.execute("SELECT * FROM workspace_organizations WHERE tenant_id=?", (tenant_id,)).fetchone())
            enabled_departments = department_keys if department_keys is not None else set(DEPARTMENTS)
            meetings = self.list_meetings(tenant_id, departments=enabled_departments)
            actions = self.list_actions(tenant_id, departments=enabled_departments)
            entities = self.list_entities(tenant_id, departments=enabled_departments)
            department_health = [
                {"key": key, "name": value["name"], "lead": value["lead"], "status": "attention" if key in {"sales", "customer_success"} else "on_track", "open_actions": sum(action["department"] == key and action["status"] != "done" for action in actions)}
                for key, value in DEPARTMENTS.items() if key in enabled_departments
            ]
            return {
                "organization": organization,
                "metrics": {"employees": organization["employee_count"], "departments": len(enabled_departments), "open_actions": sum(action["status"] != "done" for action in actions), "upcoming_meetings": sum(meeting["status"] == "scheduled" for meeting in meetings)},
                "meetings": meetings[:4],
                "actions": actions[:6],
                "departments": department_health,
                "record_catalog": [{"type": entity_type, "count": sum(entity["entity_type"] == entity_type for entity in entities)} for entity_type in sorted({entity["entity_type"] for entity in entities})],
                "is_synthetic_demo": True,
            }
        finally:
            conn.close()


def get_demo_workspace_store() -> DemoWorkspaceStore:
    return DemoWorkspaceStore()
