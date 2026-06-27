"""
infrastructure/project_context.py — Project context management.

The ProjectContextManager loads at the start of every project-scoped session.
It answers: who is this user, which project are they in, what is their
access level, what does the project's schema look like, and what is the
Tier 1 data (project_metadata + kpi summary) that every agent needs?

This context is passed to every agent call so agents are never project-blind.
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

import config
from infrastructure.tenant_manager import DEFAULT_TENANT_ID
from infrastructure.project_provisioner import get_project_provisioner

logger = logging.getLogger(__name__)


# ── Context dataclass ─────────────────────────────────────────────────────────

@dataclass
class ProjectContext:
    """
    Complete context for a project session.
    Passed to every agent call so they know exactly what project they're in,
    who is asking, and what data they're allowed to see.
    """

    # Identity
    project_id:     str
    tenant_id:      str
    user_id:        str
    user_role:      str
    member_role:    str       # 'owner' | 'manager' | 'member' | 'viewer'
    access_level:   str       # 'full' | 'manager' | 'standard' | 'readonly'

    # Project details
    project_name:   str
    dept_id:        str
    project_status: str
    project_type:   str

    # Database routing
    db_path:        str
    faiss_path:     str

    # Tier 1 data (always in context — small, always relevant)
    metadata:       dict = field(default_factory=dict)
    kpi_summary:    list = field(default_factory=list)

    # Schema (what tables and columns exist in this project's DB)
    schema:         dict = field(default_factory=dict)

    # Mode (set per query)
    mode:           str = "query"     # 'query' | 'analysis' | 'planning' | 'reporting'

    # Session info
    session_id:     Optional[str] = None
    loaded_at:      str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_prompt_context(self) -> str:
        """
        Serialize the context into a compact string for LLM prompts.
        Tier 1 data included. Raw rows are never passed — only summaries.
        """
        kpi_lines = ""
        if self.kpi_summary:
            kpi_lines = "\n".join(
                f"  - {k.get('kpi_name', '?')}: {k.get('current_value', 'N/A')} "
                f"{k.get('unit', '')} (target: {k.get('target_value', 'N/A')}, "
                f"status: {k.get('status', '?')})"
                for k in self.kpi_summary[:8]
            )
        meta = self.metadata
        return (
            f"PROJECT CONTEXT\n"
            f"  Project: {self.project_name} (ID: {self.project_id})\n"
            f"  Department: {self.dept_id}\n"
            f"  Status: {meta.get('health_status', self.project_status)}\n"
            f"  Completion: {meta.get('completion_pct', 0):.0f}%\n"
            f"  Budget: {meta.get('budget_total', 'N/A')} total, "
            f"{meta.get('budget_spent', 0)} spent, "
            f"{meta.get('budget_remaining', 'N/A')} remaining\n"
            f"  Target end: {meta.get('target_end_date', 'N/A')}\n"
            f"  User: {self.user_id} (role: {self.member_role}, "
            f"access: {self.access_level})\n"
            f"  Mode: {self.mode}\n"
            + (f"KEY KPIs:\n{kpi_lines}\n" if kpi_lines else "  No KPIs recorded yet.\n")
        )

    @property
    def can_write(self) -> bool:
        """Whether this user can trigger write-adjacent actions (agent queue)."""
        return self.member_role in ("owner", "manager") or self.access_level in ("full", "manager")

    @property
    def is_manager_level(self) -> bool:
        return self.access_level in ("full", "manager") or self.user_role in ("admin", "manager")


# ── ProjectContextManager ─────────────────────────────────────────────────────

class ProjectContextManager:
    """
    Loads and validates a ProjectContext for a given user + project + session.

    Call load() at the start of every project-scoped LLM request.
    The returned ProjectContext is passed through the agent pipeline.
    """

    def __init__(self, platform_db_path: str = config.DB_PATH):
        self._platform_db = platform_db_path

    def load(
        self,
        project_id: str,
        user_id:    str,
        tenant_id:  str = DEFAULT_TENANT_ID,
        mode:       str = "query",
        session_id: Optional[str] = None,
    ) -> ProjectContext:
        """
        Load full project context for a session.
        Raises ValueError if the user does not have access to this project.
        Raises LookupError if the project does not exist in the registry.
        """
        # 1. Verify project exists and user is a member
        project, member = self._verify_access(project_id, tenant_id, user_id)

        # 2. Get DB routing from project_registry
        registry = self._get_registry(project_id, tenant_id)
        if not registry:
            raise LookupError(
                f"Project {project_id} not found in registry — "
                "it may not be fully provisioned yet"
            )

        db_path    = registry["db_path"]
        faiss_path = registry["faiss_index_path"]

        # 3. Load Tier 1 data from project database
        metadata, kpi_summary = self._load_tier1(db_path)

        # 4. Load schema from project_schema_registry
        schema = self._load_schema(project_id, tenant_id)

        # 5. Touch last accessed
        provisioner = get_project_provisioner()
        provisioner.touch_last_accessed(project_id, tenant_id)

        ctx = ProjectContext(
            project_id=project_id,
            tenant_id=tenant_id,
            user_id=user_id,
            user_role=member.get("user_role", "employee"),
            member_role=member["role"],
            access_level=member["access_level"],
            project_name=project["name"],
            dept_id=project["primary_dept_id"],
            project_status=project["status"],
            project_type=project["project_type"],
            db_path=db_path,
            faiss_path=faiss_path,
            metadata=metadata,
            kpi_summary=kpi_summary,
            schema=schema,
            mode=mode,
            session_id=session_id,
        )

        logger.info(
            f"[ProjectContext] Loaded — project={project_id} "
            f"user={user_id} role={member['role']} mode={mode}"
        )
        return ctx

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _verify_access(
        self, project_id: str, tenant_id: str, user_id: str
    ) -> tuple[dict, dict]:
        """
        Return (project, member) dicts.
        Raises ValueError if project not found or user not a member.
        """
        conn = self._connect_platform()
        try:
            project = conn.execute(
                "SELECT * FROM projects WHERE project_id = ? AND tenant_id = ?",
                (project_id, tenant_id),
            ).fetchone()
            if not project:
                raise ValueError(f"Project {project_id} not found for tenant {tenant_id}")

            # Try joining users table for role info; fall back gracefully if users table absent
            try:
                member = conn.execute(
                    """
                    SELECT pm.*, u.role as user_role
                    FROM project_members pm
                    LEFT JOIN users u ON u.user_id = pm.user_id AND u.tenant_id = pm.tenant_id
                    WHERE pm.project_id = ? AND pm.tenant_id = ? AND pm.user_id = ? AND pm.status = 'active'
                    """,
                    (project_id, tenant_id, user_id),
                ).fetchone()
            except Exception:
                member = None

            if not member:
                # Fallback: query without users join (users table may not exist yet)
                member = conn.execute(
                    """
                    SELECT *, 'employee' as user_role
                    FROM project_members
                    WHERE project_id = ? AND tenant_id = ? AND user_id = ? AND status = 'active'
                    """,
                    (project_id, tenant_id, user_id),
                ).fetchone()

            if not member:
                raise ValueError(
                    f"User {user_id} is not a member of project {project_id}"
                )

            return dict(project), dict(member)
        finally:
            conn.close()

    def _get_registry(self, project_id: str, tenant_id: str) -> Optional[dict]:
        conn = self._connect_platform()
        try:
            row = conn.execute(
                "SELECT * FROM project_registry WHERE project_id = ? AND tenant_id = ?",
                (project_id, tenant_id),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def _load_tier1(self, db_path: str) -> tuple[dict, list]:
        """
        Load Tier 1 data: project_metadata (single row) + project_kpis summary.
        Returns (metadata_dict, kpi_list). Safe — returns empty dicts on failure.
        """
        if not Path(db_path).exists():
            logger.warning(f"[ProjectContext] DB not found at {db_path}")
            return {}, []
        try:
            conn = sqlite3.connect(db_path, timeout=10)
            conn.row_factory = sqlite3.Row

            meta_row = conn.execute("SELECT * FROM project_metadata LIMIT 1").fetchone()
            kpi_rows = conn.execute(
                "SELECT kpi_name, current_value, target_value, unit, status, trend FROM project_kpis"
            ).fetchall()

            conn.close()
            return (
                dict(meta_row) if meta_row else {},
                [dict(r) for r in kpi_rows],
            )
        except Exception as e:
            logger.warning(f"[ProjectContext] Tier 1 load failed: {e}")
            return {}, []

    def _load_schema(self, project_id: str, tenant_id: str) -> dict:
        """
        Load the registered schema for this project from project_schema_registry.
        Returns {table_name: [column_name, ...]} for agent SQL generation.
        """
        conn = self._connect_platform()
        try:
            rows = conn.execute(
                """
                SELECT table_name, column_name, data_type, is_required, description
                FROM project_schema_registry
                WHERE project_id = ? AND tenant_id = ?
                ORDER BY table_name, column_name
                """,
                (project_id, tenant_id),
            ).fetchall()

            schema: dict = {}
            for row in rows:
                tbl = row["table_name"]
                if tbl not in schema:
                    schema[tbl] = {"columns": [], "description": f"{tbl} table"}
                schema[tbl]["columns"].append(row["column_name"])

            return schema
        finally:
            conn.close()

    def _connect_platform(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._platform_db, timeout=config.DB_TIMEOUT_SECONDS)
        conn.row_factory = sqlite3.Row
        return conn


# ── Singleton ─────────────────────────────────────────────────────────────────

_context_manager: Optional[ProjectContextManager] = None


def get_project_context_manager() -> ProjectContextManager:
    global _context_manager
    if _context_manager is None:
        _context_manager = ProjectContextManager()
    return _context_manager
