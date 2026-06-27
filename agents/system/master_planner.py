from __future__ import annotations
"""
Master Planner — Tier 2 Executive Agent.
Decomposes queries → broadcasts bids → selects winners → dispatches in parallel → collects results.
"""

import asyncio
import logging
from typing import Dict, List, Optional, Tuple

import config
from models.bid_object import BidObject
from models.nl_result import NLResult
from infrastructure.llm_client import get_llm
from agents.system.query_rewriter import QueryRewriter
from agents.system.bid_selector import BidSelector

logger = logging.getLogger(__name__)


class MasterPlanner:

    def __init__(self, agent_registry: dict):
        """
        agent_registry: {dept_tag: BaseDeptAgent instance}
        """
        self.registry = agent_registry
        self.rewriter = QueryRewriter()

    # ── Decomposition ─────────────────────────────────────────────────────────

    async def decompose_query(self, query: str, user_permissions: dict) -> List[dict]:
        """
        Use LLM to break a multi-dept query into sub-queries, each tagged with a dept.
        Filters out departments the user cannot access.
        Returns list of {dept: str, sub_query: str}
        """
        llm = get_llm()
        permitted = user_permissions.get("permitted_departments", [])

        system = (
            "You decompose enterprise questions into department-specific sub-queries. "
            f"Available departments: {permitted}. "
            "Return a JSON array: "
            '[{"dept": "dept_tag", "sub_query": "the specific question for that dept"}]. '
            "Only include departments that are clearly needed. "
            "Only use departments from the available list. "
            "If the query is for one department, return a single-item array."
        )
        try:
            result = await llm.json_complete(query, system=system, strong=True)
            if isinstance(result, list):
                # Filter to only permitted departments
                return [r for r in result if r.get("dept") in permitted]
            return [{"dept": permitted[0] if permitted else "hr", "sub_query": query}]
        except Exception as e:
            logger.warning(f"Query decomposition failed: {e}")
            return [{"dept": permitted[0] if permitted else "hr", "sub_query": query}]

    # ── Bidding ───────────────────────────────────────────────────────────────

    async def broadcast_bids(self, sub_queries: List[dict]) -> Dict[str, List[BidObject]]:
        """
        Broadcast each sub-query to all registered agents simultaneously.
        Returns {sub_query_key: [BidObject, ...]}
        """
        results: Dict[str, List[BidObject]] = {}

        async def collect_bids_for_subquery(sq: dict):
            key = sq["sub_query"]
            bids = await asyncio.gather(
                *[agent.bid(sq["sub_query"]) for agent in self.registry.values()],
                return_exceptions=True,
            )
            valid_bids = [b for b in bids if isinstance(b, BidObject)]
            results[key] = valid_bids

        await asyncio.gather(*[collect_bids_for_subquery(sq) for sq in sub_queries])
        return results

    def select_winners(
        self, sub_queries: List[dict], bids_per_subquery: Dict[str, List[BidObject]]
    ) -> Tuple[Dict[str, str], List[str]]:
        """
        For each sub-query, select the winning agent.
        Delegates to BidSelector for the actual selection logic.
        """
        return BidSelector.select_winners_batch(sub_queries, bids_per_subquery)

    # ── Rewrite ───────────────────────────────────────────────────────────────

    async def rewrite_for_dispatch(
        self, sub_queries: List[dict], assignments: Dict[str, Optional[str]]
    ) -> Dict[str, str]:
        """
        Rewrite each assigned sub-query for its winning department.
        Runs all rewrites concurrently.
        Returns {original_sub_query: rewritten_query}.
        """
        return await self.rewriter.rewrite_batch(sub_queries, assignments, self.registry)

    # ── Dispatch ──────────────────────────────────────────────────────────────

    async def dispatch_parallel(
        self,
        sub_queries: List[dict],
        assignments: Dict[str, str],
        user_permissions: dict,
        rewrites: Optional[Dict[str, str]] = None,
    ) -> List[NLResult]:
        """
        Dispatch all winning agents simultaneously using asyncio.gather().
        Each agent runs its full pipeline independently.
        If `rewrites` is provided, each agent receives the rewritten query
        instead of the original sub-query.
        """
        tasks = []
        for sq in sub_queries:
            key = sq["sub_query"]
            agent_id = assignments.get(key)
            if agent_id is None:
                continue
            agent = self.registry.get(agent_id)
            if agent is None:
                logger.error(f"Agent '{agent_id}' not found in registry")
                continue
            effective_query = rewrites.get(key, key) if rewrites else key
            tasks.append(agent.execute(effective_query, user_permissions))

        if not tasks:
            return []

        results = await asyncio.gather(*tasks, return_exceptions=True)
        valid = []
        for r in results:
            if isinstance(r, Exception):
                logger.error(f"Agent execution failed: {r}")
            else:
                valid.append(r)
        return valid

    def collect_results(self, task_results: List[NLResult]) -> List[NLResult]:
        """Validate and package dept results for Fusion Agent."""
        valid = [r for r in task_results if r and r.summary]
        logger.info(f"Collected {len(valid)} dept results for fusion")
        return valid
