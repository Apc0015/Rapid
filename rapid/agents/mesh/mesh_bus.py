from __future__ import annotations
"""
mesh_bus.py — In-process async message router for agent-to-agent communication.

The MeshBus is the single point through which:
  - The Orchestrator dispatches queries to dept agents
  - C-Suite agents dispatch sub-queries across their division

No network, no serialisation — pure asyncio.gather() within one process.
If RAPID ever moves to a distributed model, only this file needs to change.
"""

import asyncio
import logging
from typing import TYPE_CHECKING, Dict, List, Optional

from models.nl_result import NLResult

if TYPE_CHECKING:
    from agents.registry import AgentRegistry

logger = logging.getLogger(__name__)


class MeshBus:
    """
    Routes queries between agents.

    Usage:
        bus = MeshBus(registry)

        # Direct unicast
        result = await bus.send("finance", query, user_permissions)

        # Parallel dispatch across multiple agents
        results = await bus.broadcast_and_execute(
            assignments={"What is Q3 revenue?": "finance"},
            perms=user_permissions,
            rewrites={"What is Q3 revenue?": "Q3 FY2026 revenue vs budget?"},
        )
    """

    def __init__(self, registry: "AgentRegistry") -> None:
        self._registry = registry

    # ── Unicast ───────────────────────────────────────────────────────────────

    async def send(
        self,
        agent_id: str,
        query: str,
        user_permissions: dict,
    ) -> NLResult:
        """
        Send a query directly to a named dept or c-suite agent.
        Returns the agent's NLResult.
        Raises KeyError if agent_id is not registered.
        """
        # Try dept agents first, then c-suite
        agent = self._registry.get_dept_agent(agent_id) or \
                self._registry.get_csuite_agent(agent_id)

        if agent is None:
            logger.error(f"MeshBus.send: unknown agent_id='{agent_id}'")
            return NLResult(
                summary=f"No agent registered for '{agent_id}'.",
                source="mesh_error",
                confidence=0.0,
                dept_tag=agent_id,
            )

        try:
            return await agent.execute(query, user_permissions)
        except Exception as exc:
            logger.error(f"MeshBus.send: agent '{agent_id}' raised {exc!r}")
            return NLResult(
                summary=f"Agent '{agent_id}' encountered an error.",
                source="mesh_error",
                confidence=0.0,
                dept_tag=agent_id,
            )

    # ── Parallel dispatch ─────────────────────────────────────────────────────

    async def broadcast_and_execute(
        self,
        assignments: Dict[str, Optional[str]],   # {sub_query: agent_id | None}
        user_permissions: dict,
        rewrites: Optional[Dict[str, str]] = None,
    ) -> List[NLResult]:
        """
        Execute all winning agents concurrently via asyncio.gather().
        Skips sub-queries where the assignment is None (gap).

        assignments: {original_sub_query: agent_id}  (None = no winner)
        rewrites:    {original_sub_query: rewritten_query}  (optional)
        """
        tasks: List[asyncio.Task] = []
        task_labels: List[str] = []

        for sub_query, agent_id in assignments.items():
            if agent_id is None:
                continue
            effective_query = (rewrites or {}).get(sub_query, sub_query)
            tasks.append(self.send(agent_id, effective_query, user_permissions))
            task_labels.append(agent_id)

        if not tasks:
            return []

        raw = await asyncio.gather(*tasks, return_exceptions=True)

        results: List[NLResult] = []
        for label, outcome in zip(task_labels, raw):
            if isinstance(outcome, Exception):
                logger.error(f"MeshBus: agent '{label}' raised exception: {outcome!r}")
            elif outcome and outcome.summary:
                results.append(outcome)
            else:
                logger.warning(f"MeshBus: agent '{label}' returned empty result — skipped")

        return results

    # ── Division broadcast (used by C-Suite agents) ───────────────────────────

    async def dispatch_to_division(
        self,
        dept_tags: List[str],
        query: str,
        user_permissions: dict,
    ) -> List[NLResult]:
        """
        Dispatch the same query to each dept in a division concurrently.
        Used by C-Suite agents to gather cross-dept data.
        """
        tasks = [self.send(dept, query, user_permissions) for dept in dept_tags]
        raw = await asyncio.gather(*tasks, return_exceptions=True)

        results: List[NLResult] = []
        for dept, outcome in zip(dept_tags, raw):
            if isinstance(outcome, Exception):
                logger.error(f"MeshBus.dispatch_to_division: '{dept}' failed: {outcome!r}")
            elif outcome and outcome.summary:
                results.append(outcome)
        return results
