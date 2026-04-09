from __future__ import annotations
"""
escalation_router.py — Hierarchy-aware escalation for low-confidence dept results.

When a dept agent returns confidence < its escalation_threshold (from hierarchy.yaml)
the EscalationRouter sends the query up to the owning C-Suite exec agent, which
re-runs the query with full division scope and returns a synthesised answer.

Escalation is transparent to the caller: you get an NLResult back either way.
"""

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Dict, Optional

import yaml

from models.nl_result import NLResult

if TYPE_CHECKING:
    from agents.registry import AgentRegistry

logger = logging.getLogger(__name__)

_HIERARCHY_PATH = Path("agents/hierarchy.yaml")


class EscalationRouter:
    """
    Reads agents/hierarchy.yaml once at construction.
    Provides:
      - should_escalate(result, dept_tag)  → bool
      - get_exec_tag(dept_tag)             → 'cfo' | 'cto' | 'coo'
      - route(dept_tag, query, initial, perms)  → NLResult
    """

    def __init__(self, registry: "AgentRegistry") -> None:
        self._registry = registry
        self._hierarchy = self._load_hierarchy()
        # Build dept → exec_tag lookup from the departments block
        self._dept_to_exec: Dict[str, str] = {}
        for dept, cfg in self._hierarchy.get("departments", {}).items():
            esc = cfg.get("escalates_to")
            if esc:
                self._dept_to_exec[dept] = esc
        logger.info(f"EscalationRouter: dept→exec map: {self._dept_to_exec}")

    # ── Public API ────────────────────────────────────────────────────────────

    def should_escalate(self, result: NLResult, dept_tag: str) -> bool:
        """
        Return True if the dept result's confidence is below the dept's
        escalation_threshold defined in hierarchy.yaml.
        """
        dept_cfg = self._hierarchy.get("departments", {}).get(dept_tag, {})
        threshold = dept_cfg.get("escalation_threshold", 0.65)
        escalate = result.confidence < threshold
        if escalate:
            logger.info(
                f"Escalation triggered: dept={dept_tag} "
                f"confidence={result.confidence:.2f} < threshold={threshold}"
            )
        return escalate

    def get_exec_tag(self, dept_tag: str) -> Optional[str]:
        """Return the exec_tag (e.g. 'cfo') for the given dept, or None."""
        return self._dept_to_exec.get(dept_tag)

    async def route(
        self,
        dept_tag: str,
        query: str,
        initial_result: NLResult,
        user_permissions: dict,
    ) -> NLResult:
        """
        Escalate a low-confidence dept result to the owning exec agent.
        The exec agent re-runs the query with full division scope.
        If no exec agent is found, returns the original (low-confidence) result.
        """
        exec_tag = self.get_exec_tag(dept_tag)
        if not exec_tag:
            logger.warning(f"No escalation target for dept='{dept_tag}' — keeping original result")
            return initial_result

        exec_agent = self._registry.get_csuite_agent(exec_tag)
        if exec_agent is None:
            logger.warning(f"Exec agent '{exec_tag}' not registered — keeping original result")
            return initial_result

        try:
            escalated = await exec_agent.handle_escalation(
                from_dept=dept_tag,
                query=query,
                initial_result=initial_result,
                user_permissions=user_permissions,
            )
            logger.info(
                f"Escalation resolved: {dept_tag} → {exec_tag} "
                f"new_confidence={escalated.confidence:.2f}"
            )
            return escalated
        except Exception as exc:
            logger.error(f"EscalationRouter: exec agent '{exec_tag}' failed: {exc!r}")
            return initial_result

    # ── Private ───────────────────────────────────────────────────────────────

    @staticmethod
    def _load_hierarchy() -> dict:
        if not _HIERARCHY_PATH.exists():
            logger.error(f"hierarchy.yaml not found at {_HIERARCHY_PATH}")
            return {}
        return yaml.safe_load(_HIERARCHY_PATH.read_text()) or {}
