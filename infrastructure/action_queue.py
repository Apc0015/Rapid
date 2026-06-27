"""
infrastructure/action_queue.py — Agent Action Queue Manager.

Implements the Human-in-the-Loop action approval workflow described in the
RAPID blueprint Section 10.

Every action an agent wants to take is categorised:

  Category A — Agent acts automatically (low-stakes, reversible, informational)
               e.g. logging, flagging, generating draft documents, KPI updates

  Category B — Agent recommends, human approves before execution
               e.g. sending reports externally, changing project status,
               budget reallocations, escalating risks

  Category C — Human decides, agent executes the mechanics
               e.g. project cancellation, major budget cuts, hiring decisions

Category A actions execute immediately (no queue entry needed).
Category B and C actions enter this queue and wait for human approval.

The queue lives in each project's SQLite database (agent_action_queue table),
which is created by ProjectProvisioner.

Usage
─────
    from infrastructure.action_queue import get_action_queue

    aq = get_action_queue(db_path, project_id, tenant_id)

    # Queue a Category B action
    action = aq.enqueue(
        agent_dept   = "finance",
        action_type  = "flag_budget_risk",
        category     = "B_approve",
        title        = "Flag Project Alpha budget as at-risk",
        description  = "Burn rate projects 23% overrun by Q3 end",
        reasoning    = "At current spend rate, project will exceed budget...",
        evidence     = {"burn_rate": 45000, "remaining_budget": 120000, "days_left": 47},
        priority     = "high",
    )

    # List pending actions
    pending = aq.list_pending()

    # Human approves
    aq.approve(action.action_id, reviewed_by="user_ayush")

    # Human rejects
    aq.reject(action.action_id, reviewed_by="user_ayush", reason="False alarm")
"""

from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)


# ── Action categories ─────────────────────────────────────────────────────────

class ActionCategory:
    A_AUTO    = "A_auto"     # Agent acts automatically
    B_APPROVE = "B_approve"  # Requires human approval
    C_HUMAN   = "C_human"    # Human decides, agent executes


class ActionStatus:
    PENDING   = "pending"
    APPROVED  = "approved"
    REJECTED  = "rejected"
    EXECUTED  = "executed"
    EXPIRED   = "expired"
    CANCELLED = "cancelled"


class ActionPriority:
    LOW    = "low"
    MEDIUM = "medium"
    HIGH   = "high"
    URGENT = "urgent"


# ── Action dataclass ──────────────────────────────────────────────────────────

@dataclass
class AgentAction:
    """
    A single action in the agent action queue.

    action_id       — UUID string
    tenant_id       — Which tenant this belongs to
    project_id      — Which project this is for
    agent_dept      — Which department agent created this
    action_type     — Machine-readable action identifier (e.g. "flag_budget_risk")
    category        — A_auto | B_approve | C_human
    title           — Short human-readable description (shown in queue UI)
    description     — Longer explanation of what the action does
    reasoning       — Why the agent wants to take this action
    evidence        — Structured data supporting the reasoning (JSON)
    output_file_path — If a document was produced, the path
    priority        — low | medium | high | urgent
    status          — pending | approved | rejected | executed | expired | cancelled
    created_at      — ISO timestamp
    reviewed_by     — user_id of the human who approved/rejected
    reviewed_at     — ISO timestamp of review
    executed_at     — ISO timestamp of execution
    rejection_reason — Reason if rejected
    session_id      — Optional linked session_id
    """
    action_id:        str
    tenant_id:        str
    project_id:       str
    agent_dept:       str
    action_type:      str
    category:         str
    title:            str
    description:      str              = ""
    reasoning:        str              = ""
    evidence:         dict             = field(default_factory=dict)
    output_file_path: Optional[str]    = None
    priority:         str              = ActionPriority.MEDIUM
    status:           str              = ActionStatus.PENDING
    created_at:       str              = field(default_factory=lambda: datetime.utcnow().isoformat())
    reviewed_by:      Optional[str]    = None
    reviewed_at:      Optional[str]    = None
    executed_at:      Optional[str]    = None
    rejection_reason: Optional[str]    = None
    session_id:       Optional[str]    = None

    def to_dict(self) -> dict:
        return {
            "action_id":        self.action_id,
            "tenant_id":        self.tenant_id,
            "project_id":       self.project_id,
            "agent_dept":       self.agent_dept,
            "action_type":      self.action_type,
            "category":         self.category,
            "title":            self.title,
            "description":      self.description,
            "reasoning":        self.reasoning,
            "evidence":         self.evidence,
            "output_file_path": self.output_file_path,
            "priority":         self.priority,
            "status":           self.status,
            "created_at":       self.created_at,
            "reviewed_by":      self.reviewed_by,
            "reviewed_at":      self.reviewed_at,
            "executed_at":      self.executed_at,
            "rejection_reason": self.rejection_reason,
            "session_id":       self.session_id,
        }


# ── ActionQueueManager ────────────────────────────────────────────────────────

class ActionQueueManager:
    """
    Manages the agent_action_queue table in a project's SQLite database.

    All writes are synchronous (SQLite is fast for small row counts).
    Reads are done in read-only mode where possible.
    """

    def __init__(self, db_path: str, project_id: str, tenant_id: str):
        self.db_path    = db_path
        self.project_id = project_id
        self.tenant_id  = tenant_id

    # ── Write operations ──────────────────────────────────────────────────────

    def enqueue(
        self,
        agent_dept:       str,
        action_type:      str,
        title:            str,
        category:         str              = ActionCategory.B_APPROVE,
        description:      str              = "",
        reasoning:        str              = "",
        evidence:         dict             = None,
        output_file_path: Optional[str]    = None,
        priority:         str              = ActionPriority.MEDIUM,
        session_id:       Optional[str]    = None,
    ) -> AgentAction:
        """
        Add an action to the queue.
        Category A actions are created with status 'executed' immediately.
        Category B and C actions are created with status 'pending'.
        """
        action = AgentAction(
            action_id        = str(uuid.uuid4()),
            tenant_id        = self.tenant_id,
            project_id       = self.project_id,
            agent_dept       = agent_dept,
            action_type      = action_type,
            category         = category,
            title            = title,
            description      = description,
            reasoning        = reasoning,
            evidence         = evidence or {},
            output_file_path = output_file_path,
            priority         = priority,
            status           = ActionStatus.EXECUTED if category == ActionCategory.A_AUTO else ActionStatus.PENDING,
            session_id       = session_id,
        )

        if action.status == ActionStatus.EXECUTED:
            action.executed_at = datetime.utcnow().isoformat()

        self._write_action(action)
        logger.info(
            f"[ActionQueue] Enqueued {action.category} action '{action.title}' "
            f"(id={action.action_id[:8]}, priority={action.priority})"
        )
        return action

    def approve(
        self,
        action_id:   str,
        reviewed_by: str,
    ) -> Optional[AgentAction]:
        """
        Approve a pending action. Sets status → approved, records reviewer.
        Returns the updated action, or None if not found / already reviewed.
        """
        action = self.get(action_id)
        if not action:
            logger.warning(f"[ActionQueue] approve: action {action_id} not found")
            return None
        if action.status != ActionStatus.PENDING:
            logger.warning(
                f"[ActionQueue] approve: action {action_id} is already '{action.status}'"
            )
            return action

        now = datetime.utcnow().isoformat()
        conn = self._connect()
        try:
            conn.execute(
                """
                UPDATE agent_action_queue
                SET status='approved', reviewed_by=?, reviewed_at=?
                WHERE action_id=?
                """,
                (reviewed_by, now, action_id),
            )
            conn.commit()
        finally:
            conn.close()

        action.status      = ActionStatus.APPROVED
        action.reviewed_by = reviewed_by
        action.reviewed_at = now
        logger.info(f"[ActionQueue] Action {action_id[:8]} APPROVED by {reviewed_by}")
        return action

    def reject(
        self,
        action_id:   str,
        reviewed_by: str,
        reason:      str = "",
    ) -> Optional[AgentAction]:
        """
        Reject a pending action. Sets status → rejected.
        Returns the updated action, or None if not found.
        """
        action = self.get(action_id)
        if not action:
            return None
        if action.status != ActionStatus.PENDING:
            return action

        now = datetime.utcnow().isoformat()
        conn = self._connect()
        try:
            conn.execute(
                """
                UPDATE agent_action_queue
                SET status='rejected', reviewed_by=?, reviewed_at=?, rejection_reason=?
                WHERE action_id=?
                """,
                (reviewed_by, now, reason, action_id),
            )
            conn.commit()
        finally:
            conn.close()

        action.status           = ActionStatus.REJECTED
        action.reviewed_by      = reviewed_by
        action.reviewed_at      = now
        action.rejection_reason = reason
        logger.info(f"[ActionQueue] Action {action_id[:8]} REJECTED by {reviewed_by}: {reason}")
        return action

    def mark_executed(self, action_id: str) -> bool:
        """Mark an approved action as executed after the agent runs it."""
        now = datetime.utcnow().isoformat()
        conn = self._connect()
        try:
            rows = conn.execute(
                "UPDATE agent_action_queue SET status='executed', executed_at=? WHERE action_id=?",
                (now, action_id),
            ).rowcount
            conn.commit()
            return rows > 0
        finally:
            conn.close()

    def expire_stale(self, older_than_days: int = 7) -> int:
        """
        Expire actions that have been pending for longer than `older_than_days`.
        Returns the number of actions expired.
        """
        cutoff = (datetime.utcnow() - timedelta(days=older_than_days)).isoformat()
        conn   = self._connect()
        try:
            rows = conn.execute(
                """
                UPDATE agent_action_queue
                SET status='expired'
                WHERE status='pending' AND created_at < ?
                """,
                (cutoff,),
            ).rowcount
            conn.commit()
            if rows:
                logger.info(f"[ActionQueue] Expired {rows} stale actions older than {older_than_days}d")
            return rows
        finally:
            conn.close()

    # ── Read operations ───────────────────────────────────────────────────────

    def get(self, action_id: str) -> Optional[AgentAction]:
        """Fetch a single action by ID."""
        conn = self._connect_ro()
        try:
            row = conn.execute(
                "SELECT * FROM agent_action_queue WHERE action_id=?",
                (action_id,),
            ).fetchone()
            return self._row_to_action(row) if row else None
        finally:
            conn.close()

    def list_pending(self) -> list[AgentAction]:
        """Return all pending (awaiting human review) actions, newest first."""
        return self._list(status=ActionStatus.PENDING)

    def list_all(
        self,
        status:    Optional[str] = None,
        category:  Optional[str] = None,
        dept:      Optional[str] = None,
        limit:     int           = 100,
    ) -> list[AgentAction]:
        """
        List actions with optional filters.
        Returns newest first.
        """
        clauses = []
        params  = []
        if status:
            clauses.append("status = ?")
            params.append(status)
        if category:
            clauses.append("category = ?")
            params.append(category)
        if dept:
            clauses.append("agent_dept = ?")
            params.append(dept)

        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        conn  = self._connect_ro()
        try:
            rows = conn.execute(
                f"SELECT * FROM agent_action_queue {where} ORDER BY created_at DESC LIMIT ?",
                (*params, limit),
            ).fetchall()
            return [self._row_to_action(r) for r in rows]
        finally:
            conn.close()

    def pending_count(self) -> int:
        """Fast count of pending actions (for dashboards)."""
        conn = self._connect_ro()
        try:
            r = conn.execute(
                "SELECT COUNT(*) FROM agent_action_queue WHERE status='pending'"
            ).fetchone()
            return r[0] if r else 0
        finally:
            conn.close()

    def stats(self) -> dict:
        """Return counts by status and category."""
        conn = self._connect_ro()
        try:
            rows = conn.execute(
                "SELECT status, COUNT(*) cnt FROM agent_action_queue GROUP BY status"
            ).fetchall()
            by_status = {r[0]: r[1] for r in rows}

            rows = conn.execute(
                "SELECT category, COUNT(*) cnt FROM agent_action_queue GROUP BY category"
            ).fetchall()
            by_cat = {r[0]: r[1] for r in rows}

            return {
                "by_status":   by_status,
                "by_category": by_cat,
                "total":       sum(by_status.values()),
            }
        finally:
            conn.close()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _list(self, status: str) -> list[AgentAction]:
        conn = self._connect_ro()
        try:
            rows = conn.execute(
                "SELECT * FROM agent_action_queue WHERE status=? ORDER BY created_at DESC",
                (status,),
            ).fetchall()
            return [self._row_to_action(r) for r in rows]
        finally:
            conn.close()

    def _write_action(self, action: AgentAction) -> None:
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO agent_action_queue
                    (action_id, tenant_id, project_id, session_id, agent_dept,
                     action_type, category, title, description, reasoning,
                     evidence, output_file_path, priority, status,
                     created_at, reviewed_by, reviewed_at, executed_at, rejection_reason)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    action.action_id,
                    action.tenant_id,
                    action.project_id,
                    action.session_id,
                    action.agent_dept,
                    action.action_type,
                    action.category,
                    action.title,
                    action.description,
                    action.reasoning,
                    json.dumps(action.evidence),
                    action.output_file_path,
                    action.priority,
                    action.status,
                    action.created_at,
                    action.reviewed_by,
                    action.reviewed_at,
                    action.executed_at,
                    action.rejection_reason,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def _row_to_action(self, row: sqlite3.Row) -> AgentAction:
        d = dict(row)
        try:
            evidence = json.loads(d.get("evidence") or "{}")
        except Exception:
            evidence = {}
        return AgentAction(
            action_id        = d["action_id"],
            tenant_id        = d["tenant_id"],
            project_id       = d["project_id"],
            agent_dept       = d["agent_dept"],
            action_type      = d["action_type"],
            category         = d["category"],
            title            = d["title"],
            description      = d.get("description") or "",
            reasoning        = d.get("reasoning") or "",
            evidence         = evidence,
            output_file_path = d.get("output_file_path"),
            priority         = d.get("priority") or ActionPriority.MEDIUM,
            status           = d.get("status") or ActionStatus.PENDING,
            created_at       = d.get("created_at") or "",
            reviewed_by      = d.get("reviewed_by"),
            reviewed_at      = d.get("reviewed_at"),
            executed_at      = d.get("executed_at"),
            rejection_reason = d.get("rejection_reason"),
            session_id       = d.get("session_id"),
        )

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=15)
        conn.row_factory = sqlite3.Row
        return conn

    def _connect_ro(self) -> sqlite3.Connection:
        conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn


# ── Convenience factory ───────────────────────────────────────────────────────

def get_action_queue(
    db_path:    str,
    project_id: str,
    tenant_id:  str,
) -> ActionQueueManager:
    """Create an ActionQueueManager for a specific project database."""
    return ActionQueueManager(db_path=db_path, project_id=project_id, tenant_id=tenant_id)
