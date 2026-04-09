from __future__ import annotations
"""
BaseDeptAgent — abstract base class for all 7 department agents.
Every department agent inherits from this.
The concrete dept class only defines: dept_tag, doc_folders, permitted_tables,
and any domain-specific bid logic or query rewriting.
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import List

from models.bid_object import BidObject
from models.nl_result import NLResult
from pipelines.rag_pipeline import run_rag_pipeline
from pipelines.db_pipeline import run_db_pipeline
from agents.governance_filter import get_governance
from infrastructure.llm_client import get_llm

logger = logging.getLogger(__name__)


class BaseDeptAgent(ABC):

    # ── Subclasses define these ───────────────────────────────────────────────
    dept_tag: str = ""
    doc_folders: List[str] = []
    permitted_tables: List[str] = []
    bid_keywords: List[str] = []          # high-confidence keyword triggers
    partial_keywords: List[str] = []      # partial-confidence triggers

    # ── Bidding ───────────────────────────────────────────────────────────────

    async def bid(self, query: str) -> BidObject:
        """
        Return a BidObject with confidence score.
        Default implementation uses keyword matching.
        Subclasses can override for smarter bidding.
        """
        q_lower = query.lower()

        exact_matches = sum(1 for kw in self.bid_keywords if kw in q_lower)
        partial_matches = sum(1 for kw in self.partial_keywords if kw in q_lower)

        if exact_matches >= 2:
            confidence = min(0.95, 0.70 + exact_matches * 0.08)
        elif exact_matches == 1:
            confidence = 0.65 + partial_matches * 0.05
        elif partial_matches >= 1:
            confidence = 0.45 + partial_matches * 0.05
        else:
            confidence = 0.10

        can_handle = confidence >= 0.30
        estimated_tokens = self._estimate_tokens(query)

        return BidObject(
            agent_id=self.dept_tag,
            can_handle=can_handle,
            confidence=round(confidence, 3),
            estimated_tokens=estimated_tokens,
            needs_web_fallback=False,
            caveats=self._get_caveats(query),
        )

    # ── Pipeline execution ────────────────────────────────────────────────────

    async def execute(self, query: str, user_permissions: dict) -> NLResult:
        """
        Run both RAG and DB pipelines in parallel, then merge.
        Governance is enriched per-dept before each pipeline.
        """
        governance = get_governance()
        dept_permissions = governance.enrich_permissions_for_dept(user_permissions, self.dept_tag)

        # Run both pipelines concurrently
        rag_result, db_result = await asyncio.gather(
            run_rag_pipeline(query, self.dept_tag, dept_permissions),
            run_db_pipeline(query, self.dept_tag, dept_permissions),
            return_exceptions=True,
        )

        # Handle exceptions from either pipeline
        if isinstance(rag_result, Exception):
            logger.error(f"RAG pipeline failed for {self.dept_tag}: {rag_result}")
            rag_result = NLResult(summary="", source="rag", confidence=0.0)
        if isinstance(db_result, Exception):
            logger.error(f"DB pipeline failed for {self.dept_tag}: {db_result}")
            db_result = NLResult(summary="", source="database", confidence=0.0)

        return await self.merge_sources(rag_result, db_result, query)

    async def merge_sources(self, rag_result: NLResult, db_result: NLResult, query: str) -> NLResult:
        """
        Combine document and database NL summaries into one coherent dept answer.
        If both have content, use LLM to merge. Otherwise, return the higher-confidence one.
        """
        has_rag = bool(rag_result.summary and rag_result.confidence > 0.2)
        has_db = bool(db_result.summary and db_result.confidence > 0.2)

        if has_rag and has_db:
            merged_summary = await self._llm_merge(rag_result, db_result, query)
            composite_conf = (
                rag_result.confidence * 0.4 + db_result.confidence * 0.6
            )
            citations = list(set(rag_result.citations + db_result.citations))
            return NLResult(
                summary=merged_summary,
                source="merged",
                confidence=round(composite_conf, 3),
                citations=citations,
                dept_tag=self.dept_tag,
                governance_log=rag_result.governance_log + db_result.governance_log,
            )
        elif has_db:
            db_result.dept_tag = self.dept_tag
            return db_result
        elif has_rag:
            rag_result.dept_tag = self.dept_tag
            return rag_result
        else:
            return NLResult(
                summary=f"No relevant information found in the {self.dept_tag.upper()} department for this query.",
                source="merged",
                confidence=0.1,
                dept_tag=self.dept_tag,
            )

    # ── Helpers ───────────────────────────────────────────────────────────────

    async def _llm_merge(self, rag: NLResult, db: NLResult, query: str) -> str:
        llm = get_llm()
        system = (
            f"You are the {self.dept_tag.upper()} department AI assistant. "
            "Merge the two information sources below into one clear, accurate answer. "
            "If they contradict each other, note both versions clearly. "
            "Do not add information not present in either source."
        )
        prompt = (
            f"Question: {query}\n\n"
            f"From documents:\n{rag.summary}\n\n"
            f"From database:\n{db.summary}"
        )
        return await llm.complete(prompt, system=system)

    def _estimate_tokens(self, query: str) -> int:
        """Rough token estimate for bid tiebreaking."""
        base = 400
        words = len(query.split())
        return base + words * 10

    def _get_caveats(self, query: str) -> str:
        return ""

    def __repr__(self):
        return f"{self.__class__.__name__}(dept={self.dept_tag})"
