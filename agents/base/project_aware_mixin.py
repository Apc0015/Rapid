"""
agents/base/project_aware_mixin.py — Project-awareness mixin for department agents.

Any department agent that includes this mixin gains the ability to:
  1. Accept a ProjectContext and route DB queries to the project's own database
  2. Use the project's registered schema instead of the department schema
  3. Prefix its answers with project-level context (metadata, KPIs)
  4. Record its activity in the project's activity log

Usage in a department agent:
    from agents.base.project_aware_mixin import ProjectAwareMixin

    class FinanceAgent(ProjectAwareMixin, BaseDeptAgent):
        ...
        async def run_with_context(self, query, project_context):
            # Use self.get_project_db(project_context) for the DB path
            # Use project_context.schema for schema routing
            ...
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


class ProjectAwareMixin:
    """
    Mixin that makes any department agent project-context aware.

    When a ProjectContext is provided, the agent:
    - Queries the project's own SQLite DB (not the department DB)
    - Uses the project's registered schema
    - Logs its activity to the project's activity_log table
    - Adds Tier 1 project data to its response context
    """

    def get_project_db_path(self, project_context) -> Optional[str]:
        """Return the DB path for the active project context."""
        if project_context and hasattr(project_context, "db_path"):
            return project_context.db_path
        return None

    def get_project_schema(self, project_context) -> dict:
        """Return the schema for the active project, or empty dict."""
        if project_context and hasattr(project_context, "schema"):
            return project_context.schema
        return {}

    def get_project_conn(self, project_context, timeout: int = 30) -> Optional[sqlite3.Connection]:
        """
        Open a read-only connection to the project database.
        Returns None if no project context or DB not found.
        """
        db_path = self.get_project_db_path(project_context)
        if not db_path:
            return None
        if not Path(db_path).exists():
            logger.warning(f"[ProjectAwareMixin] Project DB not found: {db_path}")
            return None
        conn = sqlite3.connect(
            f"file:{db_path}?mode=ro", uri=True, timeout=timeout
        )
        conn.row_factory = sqlite3.Row
        return conn

    def log_project_activity(
        self,
        project_context,
        event_type: str,
        description: str,
        related_entity: str = None,
        related_id: str = None,
    ):
        """
        Write an activity log entry to the project database.
        Silently fails — never blocks the main agent flow.
        """
        db_path = self.get_project_db_path(project_context)
        if not db_path or not Path(db_path).exists():
            return
        try:
            conn = sqlite3.connect(db_path, timeout=5)
            conn.execute(
                """
                INSERT INTO project_activity_log
                    (event_type, description, actor, related_entity, related_id, logged_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    event_type,
                    description,
                    getattr(project_context, "user_id", "agent"),
                    related_entity,
                    related_id,
                    datetime.utcnow().isoformat(),
                ),
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.debug(f"[ProjectAwareMixin] Activity log write failed (non-critical): {e}")

    def build_project_prompt_prefix(self, project_context) -> str:
        """
        Build a Tier 1 context prefix for LLM prompts.
        Adds project name, status, budget, and KPI summary above the query.
        """
        if not project_context:
            return ""
        return project_context.to_prompt_context() + "\n\n"

    def is_project_mode(self, project_context) -> bool:
        """Return True if a valid project context is present."""
        return project_context is not None and hasattr(project_context, "project_id")

    def get_effective_db_path(self, dept_tag: str, project_context) -> Optional[str]:
        """
        Return the effective DB path:
        - If project context present → project DB
        - Otherwise → fall back to department DB via dept_config
        """
        if self.is_project_mode(project_context):
            return self.get_project_db_path(project_context)
        # Fallback to department DB
        try:
            from infrastructure.dept_config import get_dept_config
            cfg = get_dept_config().get_db(dept_tag)
            if cfg.get("enabled") and cfg.get("type") == "sqlite":
                return cfg.get("path") or f"data/db/{dept_tag}.db"
        except Exception:
            pass
        return None

    async def query_project_db(
        self,
        sql: str,
        project_context,
    ) -> list[dict[str, Any]]:
        """
        Execute a validated SELECT query against the project database.
        Returns rows as list of dicts.
        Raises RuntimeError if project DB is not available.
        """
        db_path = self.get_project_db_path(project_context)
        if not db_path or not Path(db_path).exists():
            raise RuntimeError(
                f"Project database not available at: {db_path}"
            )

        conn = sqlite3.connect(
            f"file:{db_path}?mode=ro", uri=True, timeout=30
        )
        conn.row_factory = sqlite3.Row
        try:
            cursor = conn.execute(sql)
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()
