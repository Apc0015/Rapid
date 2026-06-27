"""
pipeline_merger.py — Extracted logic for merging RAG and DB pipeline results.
Simplifies BaseDeptAgent by centralizing merge, LLM composition, and citations.
"""

import logging
from typing import Optional
from models.nl_result import NLResult
from infrastructure.llm_client import get_llm
from agents.system.confidence_model import ConfidenceModel

logger = logging.getLogger(__name__)


class PipelineMerger:
    """Merges RAG and DB results into a coherent dept-level NL summary."""

    # Confidence threshold for "has content"
    CONTENT_THRESHOLD = 0.2

    @staticmethod
    async def merge_sources(
        rag_result: NLResult,
        db_result: NLResult,
        query: str,
        dept_tag: str,
    ) -> NLResult:
        """
        Merge RAG and DB results into one coherent answer.

        If both have content: use LLM to weave them together.
        If only one has content: return that one.
        If neither has content: return a "no info found" result.
        """
        has_rag = (
            bool(rag_result.summary)
            and rag_result.confidence > PipelineMerger.CONTENT_THRESHOLD
        )
        has_db = (
            bool(db_result.summary)
            and db_result.confidence > PipelineMerger.CONTENT_THRESHOLD
        )

        if has_rag and has_db:
            return await PipelineMerger._merge_both_sources(
                rag_result, db_result, query, dept_tag
            )
        elif has_db:
            db_result.dept_tag = dept_tag
            return db_result
        elif has_rag:
            rag_result.dept_tag = dept_tag
            return rag_result
        else:
            return NLResult(
                summary=f"No relevant information found in the {dept_tag.upper()} department for this query.",
                source="merged",
                confidence=0.1,
                dept_tag=dept_tag,
            )

    @staticmethod
    async def _merge_both_sources(
        rag: NLResult,
        db: NLResult,
        query: str,
        dept_tag: str,
    ) -> NLResult:
        """Merge two non-empty sources using LLM."""
        llm = get_llm()
        system = (
            f"You are the {dept_tag.upper()} department AI assistant. "
            "Merge the two information sources below into one clear, accurate answer. "
            "If they contradict, note both versions explicitly. "
            "Do not add information not present in either source."
        )
        prompt = (
            f"Question: {query}\n\n"
            f"From documents:\n{rag.summary}\n\n"
            f"From database:\n{db.summary}"
        )
        merged_summary = await llm.complete(prompt, system=system)

        # Composite confidence: prefer DB (0.6) over RAG (0.4)
        composite_conf = ConfidenceModel.merge_dept_confidences(
            rag.confidence, db.confidence
        )

        # Merge citations
        citations = list(set(rag.citations + db.citations))
        governance_log = rag.governance_log + db.governance_log

        return NLResult(
            summary=merged_summary,
            source="merged",
            confidence=composite_conf,
            citations=citations,
            dept_tag=dept_tag,
            governance_log=governance_log,
        )
