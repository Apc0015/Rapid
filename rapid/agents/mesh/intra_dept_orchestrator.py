from __future__ import annotations
"""
intra_dept_orchestrator.py — Routes within-department queries to specialist agents.

Lives inside each dept head agent. The dept head calls:
    result = await self._intra.handle(query, user_permissions)

The IntraDeptOrchestrator:
  1. Classifies which specialist(s) should handle this query (LLM, fast)
  2. Dispatches to them in parallel
  3. Merges their NL results into one coherent dept-level NLResult

The external interface of the dept head agent (bid + execute) is unchanged.
"""

import asyncio
import logging
from typing import List, TYPE_CHECKING

from models.nl_result import NLResult

if TYPE_CHECKING:
    from agents.base.base_employee_agent import BaseEmployeeAgent

logger = logging.getLogger(__name__)


class IntraDeptOrchestrator:
    """
    Within-department query router.

    Args:
        dept_tag:    e.g. "finance"
        specialists: list of BaseEmployeeAgent instances for this dept
    """

    def __init__(self, dept_tag: str, specialists: List["BaseEmployeeAgent"]) -> None:
        self._dept_tag   = dept_tag
        self._specialists = specialists
        # Fast lookup: role_title → agent
        self._by_role    = {s.role_title: s for s in specialists}

    # ── Public API ────────────────────────────────────────────────────────────

    async def handle(self, query: str, user_permissions: dict) -> NLResult:
        """
        Classify → dispatch in parallel → merge.
        Falls back to all specialists if classification fails.
        """
        assigned = await self._classify(query)

        if not assigned:
            logger.warning(
                f"IntraDeptOrchestrator[{self._dept_tag}]: "
                "classification returned no specialists — using all"
            )
            assigned = self._specialists

        # Dispatch in parallel
        raw = await asyncio.gather(
            *[s.execute(query, user_permissions) for s in assigned],
            return_exceptions=True,
        )

        results: List[NLResult] = []
        for agent, outcome in zip(assigned, raw):
            if isinstance(outcome, Exception):
                logger.error(
                    f"IntraDeptOrchestrator[{self._dept_tag}]: "
                    f"specialist '{agent.role_title}' raised: {outcome!r}"
                )
            elif outcome and outcome.summary:
                results.append(outcome)

        return self._merge(results, query)

    # ── Private ───────────────────────────────────────────────────────────────

    async def _classify(self, query: str) -> List["BaseEmployeeAgent"]:
        """
        Ask each specialist to bid, then return those with confidence >= 0.30.
        Falls back to all specialists if none qualify.
        This avoids an LLM call for classification (keyword matching is fast).
        """
        bids = await asyncio.gather(
            *[s.bid(query) for s in self._specialists],
            return_exceptions=True,
        )

        qualified = []
        for specialist, bid in zip(self._specialists, bids):
            if isinstance(bid, Exception):
                continue
            if bid.can_handle and bid.confidence >= 0.30:
                qualified.append((specialist, bid.confidence))

        if not qualified:
            return self._specialists  # fallback: use all

        # Sort by confidence desc
        qualified.sort(key=lambda x: x[1], reverse=True)

        # Return top specialists (max 3 to avoid over-querying)
        return [s for s, _ in qualified[:3]]

    def _merge(self, results: List[NLResult], query: str) -> NLResult:
        """
        Combine specialist NL summaries into one dept-level NLResult.
        Simple concatenation with role labels — keeps it transparent.
        """
        if not results:
            return NLResult(
                summary=(
                    f"No relevant information found in the "
                    f"{self._dept_tag.upper()} department for this query."
                ),
                source="intra_dept",
                confidence=0.1,
                dept_tag=self._dept_tag,
            )

        if len(results) == 1:
            r = results[0]
            r.dept_tag = self._dept_tag
            r.source   = "intra_dept"
            return r

        # Multiple specialist results — concatenate with labels
        parts = [f"**{r.governance_log[0].get('agent', 'Specialist') if r.governance_log else 'Specialist'}:** {r.summary}"
                 for r in results]
        combined_summary = "\n\n".join(parts)

        avg_confidence = round(
            sum(r.confidence for r in results) / len(results), 3
        )
        all_citations = list({c for r in results for c in (r.citations or [])})
        all_gov_logs  = [entry for r in results for entry in (r.governance_log or [])]

        return NLResult(
            summary=combined_summary,
            source="intra_dept",
            confidence=avg_confidence,
            citations=all_citations,
            dept_tag=self._dept_tag,
            governance_log=all_gov_logs,
        )

    def list_specialists(self) -> List[str]:
        return [s.role_title for s in self._specialists]
