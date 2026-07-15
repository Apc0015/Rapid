from __future__ import annotations
"""
orchestrator.py — Hierarchy-aware query orchestration.

The Orchestrator is the single entry-point that replaces the raw
decompose → bid → select → dispatch block in main.py.

It does everything MasterPlanner did, plus:
  - Routes c-suite / CEO / admin users directly to the correct exec agent
  - Escalates low-confidence dept results up the hierarchy via EscalationRouter
  - Uses AgentMemory to track in-flight context (for audit + stale cleanup)

main.py change:
    # BEFORE (raw planner block):
    sub_queries  = await planner.decompose_query(req.query, user_permissions)
    bids         = await planner.broadcast_bids(sub_queries)
    assignments, gaps = planner.select_winners(sub_queries, bids)
    ...
    dept_results = planner.collect_results(await planner.dispatch_parallel(...))

    # AFTER (single call):
    dept_results, gaps = await orchestrator.handle(
        query_id, req.query, user_permissions, intent_type
    )
"""

import logging
from typing import List, Optional, Tuple, TYPE_CHECKING

from models.nl_result import NLResult

if TYPE_CHECKING:
    from agents.system.master_planner import MasterPlanner
    from agents.registry import AgentRegistry
    from agents.mesh.mesh_bus import MeshBus
    from agents.mesh.escalation_router import EscalationRouter
    from agents.mesh.agent_memory import AgentMemory

logger = logging.getLogger(__name__)

# Roles that bypass dept agents and go straight to exec layer
_EXEC_ROLES = {"c_suite", "division_head", "ceo", "admin"}

# Role → preferred exec tag for direct routing
_ROLE_TO_EXEC = {
    "ceo":   "ceo",
    "admin": "ceo",   # admin sees everything, use CEO agent for synthesis
}


class Orchestrator:
    """
    Hierarchy-aware query orchestration replacing the raw planner block.

    Args:
        planner:  MasterPlanner — handles decompose/bid/select/rewrite
        bus:      MeshBus       — async in-process agent router
        router:   EscalationRouter — escalates low-confidence results
        memory:   AgentMemory   — per-query working memory
        registry: AgentRegistry — all registered agents
    """

    def __init__(
        self,
        planner:  "MasterPlanner",
        bus:      "MeshBus",
        router:   "EscalationRouter",
        memory:   "AgentMemory",
        registry: "AgentRegistry",
    ) -> None:
        self._planner  = planner
        self._bus      = bus
        self._router   = router
        self._memory   = memory
        self._registry = registry

    # ── Public API ────────────────────────────────────────────────────────────

    async def handle(
        self,
        query_id: str,
        query: str,
        user_permissions: dict,
        intent_type: str,
    ) -> Tuple[List[NLResult], List[str]]:
        """
        Main entry-point for the query pipeline.

        Returns:
            (dept_results, gaps)
            dept_results — list of NLResult (already escalated if needed)
            gaps         — list of sub_queries that had no winning bid
        """
        role = user_permissions.get("role", "employee")

        # Track in-flight context
        await self._memory.create(query_id, query, user_permissions)

        try:
            if role in _EXEC_ROLES:
                results = await self._exec_path(query_id, query, user_permissions, role)
                return results, []
            else:
                return await self._dept_path(query_id, query, user_permissions, intent_type)
        finally:
            await self._memory.cleanup(query_id)

    # ── Dept path (standard employees / managers) ─────────────────────────────

    async def _dept_path(
        self,
        query_id: str,
        query: str,
        user_permissions: dict,
        intent_type: str,
    ) -> Tuple[List[NLResult], List[str]]:
        """
        Standard pipeline:
          decompose → bid → select → rewrite → bus dispatch → escalation check
        """
        # Decompose
        sub_queries = await self._planner.decompose_query(query, user_permissions)

        # Bid
        bids = await self._planner.broadcast_bids(sub_queries)

        # Select winners
        assignments, gaps = self._planner.select_winners(sub_queries, bids)

        if not any(assignments.values()):
            return [], sub_queries  # all gaps → caller falls back to general LLM

        # Rewrite
        rewrites = await self._planner.rewrite_for_dispatch(sub_queries, assignments)

        # Dispatch via bus (parallel)
        dept_results = await self._bus.broadcast_and_execute(
            assignments=assignments,
            user_permissions=user_permissions,
            rewrites=rewrites,
        )

        # Escalation check: for each result, escalate if confidence < threshold
        final_results: List[NLResult] = []
        for result in dept_results:
            if result.dept_tag and self._router.should_escalate(result, result.dept_tag):
                await self._memory.mark_escalation(query_id, result.dept_tag)
                result = await self._router.route(
                    dept_tag=result.dept_tag,
                    query=query,
                    initial_result=result,
                    user_permissions=user_permissions,
                )
            final_results.append(result)

        return final_results, gaps

    # ── Exec path (c-suite / ceo / admin users) ───────────────────────────────

    async def _exec_path(
        self,
        query_id: str,
        query: str,
        user_permissions: dict,
        role: str,
    ) -> List[NLResult]:
        """
        Route directly to the appropriate C-Suite agent.
        The exec agent internally dispatches to its division depts via the bus.
        """
        exec_tag = self._resolve_exec_for_user(role, user_permissions)

        if exec_tag is None:
            # Fall back to dept path if we can't determine the right exec
            logger.warning(f"Orchestrator: could not resolve exec for role='{role}' — falling back to dept path")
            results, _ = await self._dept_path(query_id, query, user_permissions, "")
            return results

        exec_agent = self._registry.get_csuite_agent(exec_tag)
        if exec_agent is None:
            logger.error(f"Orchestrator: exec agent '{exec_tag}' not in registry — falling back to dept path")
            results, _ = await self._dept_path(query_id, query, user_permissions, "")
            return results

        try:
            result = await exec_agent.execute(query, user_permissions)
            return [result]
        except Exception as exc:
            logger.error(f"Orchestrator: exec agent '{exec_tag}' failed: {exc!r}")
            results, _ = await self._dept_path(query_id, query, user_permissions, "")
            return results

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _resolve_exec_for_user(
        self, role: str, user_permissions: dict
    ) -> Optional[str]:
        """
        Determine which exec agent to route to based on role.

        ceo / admin     → ceo agent (sees everything)
        c_suite         → determine from user's department / division
        division_head   → determine from user's division
        """
        if role in ("ceo", "admin"):
            return "ceo"

        # For c_suite / division_head: use the user's dept to find their exec
        dept = user_permissions.get("department", "")
        if dept:
            exec_agent = self._registry.get_exec_for_dept(dept)
            if exec_agent:
                return exec_agent.agent_id

        # If no dept, default to CEO for full-scope answer
        logger.info(f"Orchestrator: no dept for role='{role}' — routing to ceo")
        return "ceo"
