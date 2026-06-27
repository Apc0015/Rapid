from __future__ import annotations
"""
BaseDeptAgent — abstract base class for all department agents.
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
from agents.system.governance_filter import get_governance
from agents.system.pipeline_merger import PipelineMerger

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
        Merge RAG and DB pipeline results into a coherent dept-level answer.
        Delegates to PipelineMerger for the actual merge logic.
        """
        return await PipelineMerger.merge_sources(rag_result, db_result, query, self.dept_tag)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _estimate_tokens(self, query: str) -> int:
        """
        Structured token estimate for bid tiebreaking.

        Formula accounts for actual dept complexity, not just query length:
          query_tokens     — ~1.3 tokens per word (GPT tokeniser approximation)
          schema_tokens    — each table costs ~50 tokens in the D3 prompt; each
                             column in the rich format adds ~15 tokens (name+type+desc)
          rag_tokens       — each doc folder adds ~200 tokens of retrieved context
          specialist_tokens— each employee specialist adds ~30 tokens of routing overhead
          response_tokens  — fixed 300-token budget for the NL summary output

        Lower total = preferred in tiebreaking (faster, cheaper).
        """
        import config

        # ── Query complexity ──────────────────────────────────────────────────
        words         = len(query.split())
        query_tokens  = int(words * 1.3)

        # ── Schema complexity (D3 SQL generation prompt) ──────────────────────
        schema_tokens = 0
        try:
            schema_path = config.SCHEMA_DIR + f"/{self.dept_tag}.json"
            import json, pathlib
            if pathlib.Path(schema_path).exists():
                schema = json.loads(pathlib.Path(schema_path).read_text())
                for table_meta in schema.values():
                    cols = table_meta.get("columns", [])
                    # Rich dict format — more descriptive, more tokens
                    if isinstance(cols, dict):
                        schema_tokens += 50 + len(cols) * 15
                    else:
                        schema_tokens += 50 + len(cols) * 6
        except Exception:
            schema_tokens = 200  # safe fallback

        # ── RAG retrieval complexity ──────────────────────────────────────────
        rag_tokens = len(getattr(self, "doc_folders", [])) * 200

        # ── Intra-dept specialist routing overhead ────────────────────────────
        specialist_tokens = 0
        if hasattr(self, "_intra") and hasattr(self._intra, "_specialists"):
            specialist_tokens = len(self._intra._specialists) * 30

        # ── Fixed response budget ─────────────────────────────────────────────
        response_tokens = 300

        total = query_tokens + schema_tokens + rag_tokens + specialist_tokens + response_tokens
        return total

    def _get_caveats(self, query: str) -> str:
        return ""

    def __repr__(self):
        return f"{self.__class__.__name__}(dept={self.dept_tag})"
