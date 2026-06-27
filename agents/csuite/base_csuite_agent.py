from __future__ import annotations
"""
base_csuite_agent.py — Abstract base for all C-Suite executive agents.

C-Suite agents differ from dept agents in three ways:
  1. They own a division of departments (multi-dept scope)
  2. They handle escalations from dept agents that fell below confidence threshold
  3. They produce board-level / executive-style NL summaries

MeshBus injection:
  The bus is injected via set_bus() after the registry and bus are both
  constructed (see AgentRegistry.build()).  Until then, _bus is None and
  execute() will raise if called prematurely.
"""

import logging
from abc import ABC, abstractmethod
from typing import List, Optional, TYPE_CHECKING

from agents.base.agent_contract import AgentContract, BidObject, NLResult
from infrastructure.llm_client import get_llm

if TYPE_CHECKING:
    from agents.mesh.mesh_bus import MeshBus

logger = logging.getLogger(__name__)


class BaseCsuiteAgent(AgentContract, ABC):
    """
    Abstract base for CFO, CTO, COO, and CEO agents.

    Subclasses must define:
        exec_tag: str              — 'cfo' | 'cto' | 'coo' | 'ceo'
        division_depts: List[str]  — dept tags this exec owns
        bid_keywords: List[str]   — high-confidence keyword triggers
    """

    # ── Subclasses define these ───────────────────────────────────────────────
    exec_tag: str = ""
    division_depts: List[str] = []
    bid_keywords: List[str] = []

    def __init__(self) -> None:
        self._bus: Optional["MeshBus"] = None

    # ── AgentContract ─────────────────────────────────────────────────────────

    @property
    def agent_id(self) -> str:
        return self.exec_tag

    async def bid(self, query: str) -> BidObject:
        """
        Keyword-based bid across the executive's scope.
        C-Suite agents should win only on clearly cross-divisional or
        strategic queries — not single-dept queries.
        """
        q_lower = query.lower()
        exact = sum(1 for kw in self.bid_keywords if kw in q_lower)

        if exact >= 2:
            confidence = min(0.92, 0.72 + exact * 0.07)
        elif exact == 1:
            confidence = 0.62
        else:
            confidence = 0.08

        return BidObject(
            agent_id=self.exec_tag,
            can_handle=confidence >= 0.30,
            confidence=round(confidence, 3),
            estimated_tokens=600,
            needs_web_fallback=False,
            caveats="Executive summary — department-level detail may differ.",
        )

    async def execute(self, query: str, user_permissions: dict) -> NLResult:
        """
        Dispatch the query to all division depts via the bus, then
        synthesise an executive-level NL answer.
        """
        if self._bus is None:
            raise RuntimeError(
                f"{self.__class__.__name__}: MeshBus not injected. "
                "Call set_bus() before execute()."
            )

        dept_results = await self._bus.dispatch_to_division(
            self.division_depts, query, user_permissions
        )

        if not dept_results:
            return NLResult(
                summary=(
                    f"No relevant information found across the "
                    f"{self.exec_tag.upper()} division for this query."
                ),
                source="csuite",
                confidence=0.1,
                dept_tag=self.exec_tag,
            )

        return await self._synthesise(query, dept_results, escalation_context=None)

    # ── Escalation handler ────────────────────────────────────────────────────

    async def handle_escalation(
        self,
        from_dept: str,
        query: str,
        initial_result: NLResult,
        user_permissions: dict,
    ) -> NLResult:
        """
        Receive a low-confidence result from a dept agent.
        Re-runs with full division scope, flags the escalation in the summary.
        """
        if self._bus is None:
            logger.warning(f"{self.exec_tag}: bus not injected during escalation — returning initial result")
            return initial_result

        # Pull data from all division depts except the one that escalated
        # (which already returned low-confidence data we have as initial_result)
        other_depts = [d for d in self.division_depts if d != from_dept]
        supplemental = await self._bus.dispatch_to_division(
            other_depts, query, user_permissions
        ) if other_depts else []

        all_results = [initial_result] + supplemental
        return await self._synthesise(
            query,
            all_results,
            escalation_context=f"Escalated from {from_dept} (confidence {initial_result.confidence:.0%})",
        )

    # ── Bus injection ─────────────────────────────────────────────────────────

    def set_bus(self, bus: "MeshBus") -> None:
        """Inject the MeshBus after construction."""
        self._bus = bus

    # ── Private synthesis ─────────────────────────────────────────────────────

    async def _synthesise(
        self,
        query: str,
        dept_results: List[NLResult],
        escalation_context: Optional[str],
    ) -> NLResult:
        """
        LLM synthesis of multiple dept NL summaries into one executive answer.
        The LLM only sees NL summaries — never raw rows or chunks.
        """
        llm = get_llm()
        exec_style = self._reply_style()

        # Build context block from dept summaries (NL only)
        context_block = "\n\n".join(
            f"[{r.dept_tag.upper()}]: {r.summary}" for r in dept_results if r.summary
        )

        escalation_note = f"\n\nNote: {escalation_context}" if escalation_context else ""

        system = (
            f"You are the {self.exec_tag.upper()} AI assistant. "
            f"{exec_style} "
            "You receive natural-language summaries from department agents. "
            "Synthesise them into one clear executive answer. "
            "Do not invent data not present in the summaries. "
            "If sources conflict, note both versions."
        )

        prompt = (
            f"Question: {query}{escalation_note}\n\n"
            f"Department summaries:\n{context_block}"
        )

        try:
            answer = await llm.complete(prompt, system=system)
        except Exception as exc:
            logger.error(f"{self.exec_tag} synthesis failed: {exc!r}")
            answer = context_block or "No data available."

        # Composite confidence: weighted average of dept confidences
        confidences = [r.confidence for r in dept_results if r.confidence > 0]
        composite = round(sum(confidences) / len(confidences), 3) if confidences else 0.3

        all_citations = [c for r in dept_results for c in (r.citations or [])]

        return NLResult(
            summary=answer,
            source="csuite",
            confidence=composite,
            citations=list(set(all_citations)),
            dept_tag=self.exec_tag,
            governance_log=[
                {"check": "csuite_synthesis", "exec": self.exec_tag, "depts": [r.dept_tag for r in dept_results]}
            ],
        )

    @abstractmethod
    def _reply_style(self) -> str:
        """Return a brief style instruction for this exec's LLM synthesis."""
        ...

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(exec={self.exec_tag}, division={self.division_depts})"
