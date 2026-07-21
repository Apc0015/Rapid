"""
orgos/store.py — Persistence for the digital organization.

One SQLite database (data/orgos.db) holds four run-machinery tables plus a
generic `records` table that acts as the organization's *system of record*.

Why a records table matters: verification in this system is not "the agent
said it did it." A specialist writes real structured state into `records`
(an employee row, a provisioned-account row, a calendar entry), and the
Verifier independently reads `records` back to confirm the state actually
exists before a step is allowed to pass. The database IS the real state, so
checking it is real verification — not a mock.

Everything here is department-agnostic. Tables carry a `department` column so
HR, Finance, IT, etc. share one ledger without colliding.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from orgos.models import (
    TaskRun, RunStep, Escalation, AuditEntry,
)

logger = logging.getLogger(__name__)

DEFAULT_DB = "data/orgos.db"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class OrgStore:
    def __init__(self, db_path: str = DEFAULT_DB):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    # ── connections ────────────────────────────────────────────────────────────

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=15)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_schema(self) -> None:
        conn = self._connect()
        try:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS task_runs (
                    run_id           TEXT PRIMARY KEY,
                    tenant_id        TEXT NOT NULL DEFAULT 'default',
                    department       TEXT NOT NULL,
                    playbook         TEXT NOT NULL,
                    title            TEXT NOT NULL,
                    subject          TEXT,
                    trigger_type     TEXT,
                    trigger_payload  TEXT,
                    status           TEXT NOT NULL,
                    created_by       TEXT,
                    assigned_lead    TEXT,
                    digest_line      TEXT,
                    created_at       TEXT,
                    updated_at       TEXT,
                    parent_run_id    TEXT,
                    mesh_group_id    TEXT
                );

                CREATE TABLE IF NOT EXISTS run_steps (
                    step_id        TEXT PRIMARY KEY,
                    run_id         TEXT NOT NULL,
                    seq            INTEGER,
                    key            TEXT,
                    title          TEXT,
                    owner          TEXT,
                    autonomy       TEXT,
                    handler        TEXT,
                    verify         TEXT,
                    status         TEXT,
                    description    TEXT,
                    escalate_reason TEXT,
                    evidence       TEXT,
                    verify_result  TEXT,
                    verified_by    TEXT,
                    result_summary TEXT,
                    error          TEXT,
                    started_at     TEXT,
                    finished_at    TEXT,
                    FOREIGN KEY (run_id) REFERENCES task_runs(run_id)
                );

                CREATE TABLE IF NOT EXISTS escalations (
                    escalation_id  TEXT PRIMARY KEY,
                    run_id         TEXT NOT NULL,
                    tenant_id      TEXT NOT NULL DEFAULT 'default',
                    step_id        TEXT,
                    department     TEXT,
                    title          TEXT,
                    reason         TEXT,
                    autonomy       TEXT,
                    status         TEXT,
                    created_at     TEXT,
                    decided_by     TEXT,
                    decided_at     TEXT,
                    decision_note  TEXT
                );

                CREATE TABLE IF NOT EXISTS audit_log (
                    entry_id    TEXT PRIMARY KEY,
                    run_id      TEXT,
                    tenant_id   TEXT NOT NULL DEFAULT 'default',
                    step_id     TEXT,
                    department  TEXT,
                    actor       TEXT,
                    event       TEXT,
                    detail      TEXT,
                    at          TEXT
                );

                -- The organization's system of record. Specialists write real
                -- state here; the Verifier reads it back to confirm work.
                CREATE TABLE IF NOT EXISTS records (
                    record_id    TEXT PRIMARY KEY,
                    tenant_id    TEXT NOT NULL DEFAULT 'default',
                    department   TEXT,
                    record_type  TEXT,
                    subject      TEXT,
                    run_id       TEXT,
                    data         TEXT,
                    created_at   TEXT,
                    updated_at   TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_steps_run   ON run_steps(run_id);
                CREATE INDEX IF NOT EXISTS idx_runs_dept    ON task_runs(tenant_id, department, status);
                CREATE INDEX IF NOT EXISTS idx_esc_status   ON escalations(tenant_id, department, status);
                CREATE INDEX IF NOT EXISTS idx_audit_run    ON audit_log(run_id);
                CREATE INDEX IF NOT EXISTS idx_records_look ON records(tenant_id, department, record_type, subject);
                """
            )
            conn.commit()
            self._migrate_mesh_columns(conn)
        finally:
            conn.close()

    def _migrate_mesh_columns(self, conn: sqlite3.Connection) -> None:
        """Add columns to tables created before they existed (mesh links + tenant id)."""
        run_cols = {row[1] for row in conn.execute("PRAGMA table_info(task_runs)").fetchall()}
        for col in ("parent_run_id", "mesh_group_id"):
            if col not in run_cols:
                conn.execute(f"ALTER TABLE task_runs ADD COLUMN {col} TEXT")
        # Multi-tenant isolation: every run / record / escalation / audit row
        # carries a tenant_id. Pre-existing rows backfill to the 'default' tenant.
        for table in ("task_runs", "escalations", "audit_log", "records"):
            cols = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
            if "tenant_id" not in cols:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN tenant_id TEXT NOT NULL DEFAULT 'default'")
        conn.commit()

    # ── runs ───────────────────────────────────────────────────────────────────

    def save_run(self, run: TaskRun) -> None:
        conn = self._connect()
        try:
            conn.execute(
                """INSERT INTO task_runs
                   (run_id, tenant_id, department, playbook, title, subject, trigger_type,
                    trigger_payload, status, created_by, assigned_lead, digest_line,
                    created_at, updated_at, parent_run_id, mesh_group_id)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (run.run_id, run.tenant_id, run.department, run.playbook, run.title, run.subject,
                 run.trigger_type, json.dumps(run.trigger_payload), run.status,
                 run.created_by, run.assigned_lead, run.digest_line,
                 run.created_at, run.updated_at, run.parent_run_id, run.mesh_group_id),
            )
            for step in run.steps:
                self._insert_step(conn, step)
            conn.commit()
        finally:
            conn.close()

    def update_run(self, run: TaskRun) -> None:
        run.updated_at = _now()
        conn = self._connect()
        try:
            conn.execute(
                """UPDATE task_runs SET status=?, assigned_lead=?, digest_line=?,
                   updated_at=? WHERE run_id=?""",
                (run.status, run.assigned_lead, run.digest_line, run.updated_at, run.run_id),
            )
            conn.commit()
        finally:
            conn.close()

    def update_step(self, step: RunStep) -> None:
        conn = self._connect()
        try:
            conn.execute(
                """UPDATE run_steps SET status=?, evidence=?, verify_result=?,
                   verified_by=?, result_summary=?, error=?, started_at=?, finished_at=?
                   WHERE step_id=?""",
                (step.status, json.dumps(step.evidence), json.dumps(step.verify_result),
                 step.verified_by, step.result_summary, step.error,
                 step.started_at, step.finished_at, step.step_id),
            )
            conn.commit()
        finally:
            conn.close()

    def _insert_step(self, conn: sqlite3.Connection, step: RunStep) -> None:
        conn.execute(
            """INSERT INTO run_steps
               (step_id, run_id, seq, key, title, owner, autonomy, handler, verify,
                status, description, escalate_reason, evidence, verify_result,
                verified_by, result_summary, error, started_at, finished_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (step.step_id, step.run_id, step.seq, step.key, step.title, step.owner,
             step.autonomy, step.handler, step.verify, step.status, step.description,
             step.escalate_reason, json.dumps(step.evidence), json.dumps(step.verify_result),
             step.verified_by, step.result_summary, step.error,
             step.started_at, step.finished_at),
        )

    def get_run(self, run_id: str, tenant_id: Optional[str] = None) -> Optional[TaskRun]:
        conn = self._connect()
        try:
            if tenant_id is not None:
                row = conn.execute("SELECT * FROM task_runs WHERE run_id=? AND tenant_id=?",
                                   (run_id, tenant_id)).fetchone()
            else:
                row = conn.execute("SELECT * FROM task_runs WHERE run_id=?", (run_id,)).fetchone()
            if not row:
                return None
            run = self._row_to_run(row)
            step_rows = conn.execute(
                "SELECT * FROM run_steps WHERE run_id=? ORDER BY seq", (run_id,)
            ).fetchall()
            run.steps = [self._row_to_step(r) for r in step_rows]
            return run
        finally:
            conn.close()

    def list_runs(self, department: Optional[str] = None,
                  status: Optional[str] = None, limit: int = 200,
                  tenant_id: Optional[str] = None) -> list[TaskRun]:
        clauses, params = [], []
        if tenant_id is not None:
            clauses.append("tenant_id=?"); params.append(tenant_id)
        if department:
            clauses.append("department=?"); params.append(department)
        if status:
            clauses.append("status=?"); params.append(status)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        conn = self._connect()
        try:
            rows = conn.execute(
                f"SELECT * FROM task_runs {where} ORDER BY created_at DESC LIMIT ?",
                (*params, limit),
            ).fetchall()
            runs = [self._row_to_run(r) for r in rows]
            # attach steps in one pass
            for run in runs:
                step_rows = conn.execute(
                    "SELECT * FROM run_steps WHERE run_id=? ORDER BY seq", (run.run_id,)
                ).fetchall()
                run.steps = [self._row_to_step(r) for r in step_rows]
            return runs
        finally:
            conn.close()

    def list_runs_by_mesh_group(self, mesh_group_id: str,
                                tenant_id: Optional[str] = None) -> list[TaskRun]:
        """Every run (across every department) that belongs to one cross-department task."""
        conn = self._connect()
        try:
            if tenant_id is not None:
                rows = conn.execute(
                    "SELECT * FROM task_runs WHERE (mesh_group_id=? OR run_id=?) AND tenant_id=? ORDER BY created_at",
                    (mesh_group_id, mesh_group_id, tenant_id),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM task_runs WHERE mesh_group_id=? OR run_id=? ORDER BY created_at",
                    (mesh_group_id, mesh_group_id),
                ).fetchall()
            runs = [self._row_to_run(r) for r in rows]
            for run in runs:
                step_rows = conn.execute(
                    "SELECT * FROM run_steps WHERE run_id=? ORDER BY seq", (run.run_id,)
                ).fetchall()
                run.steps = [self._row_to_step(r) for r in step_rows]
            return runs
        finally:
            conn.close()

    # ── escalations ────────────────────────────────────────────────────────────

    def save_escalation(self, esc: Escalation) -> None:
        conn = self._connect()
        try:
            conn.execute(
                """INSERT INTO escalations
                   (escalation_id, run_id, tenant_id, step_id, department, title, reason,
                    autonomy, status, created_at, decided_by, decided_at, decision_note)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (esc.escalation_id, esc.run_id, esc.tenant_id, esc.step_id, esc.department, esc.title,
                 esc.reason, esc.autonomy, esc.status, esc.created_at,
                 esc.decided_by, esc.decided_at, esc.decision_note),
            )
            conn.commit()
        finally:
            conn.close()

    def update_escalation(self, esc: Escalation) -> None:
        conn = self._connect()
        try:
            conn.execute(
                """UPDATE escalations SET status=?, decided_by=?, decided_at=?,
                   decision_note=? WHERE escalation_id=?""",
                (esc.status, esc.decided_by, esc.decided_at, esc.decision_note,
                 esc.escalation_id),
            )
            conn.commit()
        finally:
            conn.close()

    def get_escalation(self, escalation_id: str, tenant_id: Optional[str] = None) -> Optional[Escalation]:
        conn = self._connect()
        try:
            if tenant_id is not None:
                row = conn.execute(
                    "SELECT * FROM escalations WHERE escalation_id=? AND tenant_id=?",
                    (escalation_id, tenant_id)).fetchone()
            else:
                row = conn.execute(
                    "SELECT * FROM escalations WHERE escalation_id=?", (escalation_id,)
                ).fetchone()
            return self._row_to_escalation(row) if row else None
        finally:
            conn.close()

    def list_escalations(self, department: Optional[str] = None,
                         status: Optional[str] = None,
                         tenant_id: Optional[str] = None) -> list[Escalation]:
        clauses, params = [], []
        if tenant_id is not None:
            clauses.append("tenant_id=?"); params.append(tenant_id)
        if department:
            clauses.append("department=?"); params.append(department)
        if status:
            clauses.append("status=?"); params.append(status)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        conn = self._connect()
        try:
            rows = conn.execute(
                f"SELECT * FROM escalations {where} ORDER BY created_at DESC", tuple(params)
            ).fetchall()
            return [self._row_to_escalation(r) for r in rows]
        finally:
            conn.close()

    # ── audit ──────────────────────────────────────────────────────────────────

    def append_audit(self, entry: AuditEntry) -> None:
        conn = self._connect()
        try:
            conn.execute(
                """INSERT INTO audit_log
                   (entry_id, run_id, tenant_id, step_id, department, actor, event, detail, at)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (entry.entry_id, entry.run_id, entry.tenant_id, entry.step_id, entry.department,
                 entry.actor, entry.event, entry.detail, entry.at),
            )
            conn.commit()
        finally:
            conn.close()

    def list_audit(self, run_id: Optional[str] = None,
                   department: Optional[str] = None, limit: int = 500,
                   tenant_id: Optional[str] = None) -> list[dict]:
        clauses, params = [], []
        if tenant_id is not None:
            clauses.append("tenant_id=?"); params.append(tenant_id)
        if run_id:
            clauses.append("run_id=?"); params.append(run_id)
        if department:
            clauses.append("department=?"); params.append(department)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        conn = self._connect()
        try:
            rows = conn.execute(
                f"SELECT * FROM audit_log {where} ORDER BY at ASC LIMIT ?",
                (*params, limit),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    # ── records (the system of record) ─────────────────────────────────────────

    def put_record(self, department: str, record_type: str, subject: str,
                   data: dict, run_id: str = "", tenant_id: str = "default") -> str:
        """Insert or update a record keyed by (tenant_id, department, record_type, subject)."""
        conn = self._connect()
        try:
            existing = conn.execute(
                "SELECT record_id FROM records WHERE tenant_id=? AND department=? AND record_type=? AND subject=?",
                (tenant_id, department, record_type, subject),
            ).fetchone()
            now = _now()
            if existing:
                rid = existing["record_id"]
                conn.execute(
                    "UPDATE records SET data=?, updated_at=?, run_id=? WHERE record_id=?",
                    (json.dumps(data), now, run_id, rid),
                )
            else:
                import uuid
                rid = f"rec_{uuid.uuid4().hex[:12]}"
                conn.execute(
                    """INSERT INTO records
                       (record_id, tenant_id, department, record_type, subject, run_id, data, created_at, updated_at)
                       VALUES (?,?,?,?,?,?,?,?,?)""",
                    (rid, tenant_id, department, record_type, subject, run_id, json.dumps(data), now, now),
                )
            conn.commit()
            return rid
        finally:
            conn.close()

    def find_record(self, department: str, record_type: str, subject: str,
                    tenant_id: str = "default") -> Optional[dict]:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM records WHERE tenant_id=? AND department=? AND record_type=? AND subject=?",
                (tenant_id, department, record_type, subject),
            ).fetchone()
            if not row:
                return None
            d = dict(row)
            try:
                d["data"] = json.loads(d.get("data") or "{}")
            except Exception:
                d["data"] = {}
            return d
        finally:
            conn.close()

    def list_records(self, department: Optional[str] = None,
                     record_type: Optional[str] = None, subject: Optional[str] = None,
                     tenant_id: Optional[str] = None) -> list[dict]:
        clauses, params = [], []
        for col, val in (("tenant_id", tenant_id), ("department", department),
                         ("record_type", record_type), ("subject", subject)):
            if val is not None:
                clauses.append(f"{col}=?"); params.append(val)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        conn = self._connect()
        try:
            rows = conn.execute(
                f"SELECT * FROM records {where} ORDER BY updated_at DESC", tuple(params)
            ).fetchall()
            out = []
            for r in rows:
                d = dict(r)
                try:
                    d["data"] = json.loads(d.get("data") or "{}")
                except Exception:
                    d["data"] = {}
                out.append(d)
            return out
        finally:
            conn.close()

    # ── row mappers ────────────────────────────────────────────────────────────

    def _row_to_run(self, row: sqlite3.Row) -> TaskRun:
        d = dict(row)
        try:
            payload = json.loads(d.get("trigger_payload") or "{}")
        except Exception:
            payload = {}
        return TaskRun(
            run_id=d["run_id"], department=d["department"], playbook=d["playbook"],
            title=d["title"], subject=d.get("subject") or "",
            trigger_type=d.get("trigger_type") or "", trigger_payload=payload,
            tenant_id=d.get("tenant_id") or "default",
            status=d["status"], created_by=d.get("created_by") or "",
            assigned_lead=d.get("assigned_lead") or "", digest_line=d.get("digest_line") or "",
            created_at=d.get("created_at") or "", updated_at=d.get("updated_at") or "",
            parent_run_id=d.get("parent_run_id"), mesh_group_id=d.get("mesh_group_id"),
        )

    def _row_to_step(self, row: sqlite3.Row) -> RunStep:
        d = dict(row)
        def _j(k):
            try:
                return json.loads(d.get(k) or "{}")
            except Exception:
                return {}
        return RunStep(
            step_id=d["step_id"], run_id=d["run_id"], seq=d["seq"], key=d["key"],
            title=d["title"], owner=d["owner"], autonomy=d["autonomy"],
            handler=d["handler"], verify=d["verify"], status=d["status"],
            description=d.get("description") or "", escalate_reason=d.get("escalate_reason") or "",
            evidence=_j("evidence"), verify_result=_j("verify_result"),
            verified_by=d.get("verified_by"), result_summary=d.get("result_summary") or "",
            error=d.get("error") or "", started_at=d.get("started_at"),
            finished_at=d.get("finished_at"),
        )

    def _row_to_escalation(self, row: sqlite3.Row) -> Escalation:
        d = dict(row)
        return Escalation(
            escalation_id=d["escalation_id"], run_id=d["run_id"], step_id=d.get("step_id"),
            department=d.get("department") or "", tenant_id=d.get("tenant_id") or "default",
            title=d.get("title") or "",
            reason=d.get("reason") or "", autonomy=d.get("autonomy") or "",
            status=d.get("status") or "pending", created_at=d.get("created_at") or "",
            decided_by=d.get("decided_by"), decided_at=d.get("decided_at"),
            decision_note=d.get("decision_note") or "",
        )


# ── singleton ──────────────────────────────────────────────────────────────────
_store: Optional[OrgStore] = None


def get_store(db_path: str = DEFAULT_DB) -> OrgStore:
    global _store
    if _store is None:
        _store = OrgStore(db_path)
    return _store
