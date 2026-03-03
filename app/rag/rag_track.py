"""
RAG Track — orchestrates R1→R2→R3→R4 for a single query.

Used by MasterAgent to run document retrieval in parallel with the DB track.
"""

import logging
from dataclasses import dataclass, field
from typing import List, Optional

from app.rag.r1_classifier import DocumentClassifier
from app.rag.r2_rewriter import QueryRewriter
from app.rag.r3_retriever import ChunkRetriever
from app.rag.r4_summarizer import NLSummarizer, RAGSummaryResult, RAGSourceCitation
from app.services.embedding_service import EmbeddingManager

logger = logging.getLogger(__name__)


class RAGTrack:
    """Runs the RAG pipeline for a query. Returns only NL summary."""

    def __init__(
        self,
        classifier: DocumentClassifier,
        rewriter: QueryRewriter,
        retriever: ChunkRetriever,
        summarizer: NLSummarizer,
        embedding_manager: EmbeddingManager,
    ):
        self.classifier = classifier
        self.rewriter = rewriter
        self.retriever = retriever
        self.summarizer = summarizer
        self.embedding_manager = embedding_manager

    async def run(self, raw_query: str, doc_type_hint: Optional[str] = None) -> RAGSummaryResult:
        """
        Execute R2→R3→R4 for a query.
        (R1 is used at upload time; here we use the doc_type_hint if known)
        """
        # R2 — rewrite query
        rewrite = await self.rewriter.rewrite(raw_query, doc_type=doc_type_hint or "narrative")

        # Determine top_k based on doc type hint
        top_k = 5
        if doc_type_hint:
            from app.rag.r1_classifier import _TOP_K_HINTS
            top_k = _TOP_K_HINTS.get(doc_type_hint, 5)

        # R3 — retrieve chunks
        chunks = await self.retriever.retrieve(
            rewrite_result=rewrite,
            embedding_manager=self.embedding_manager,
            top_k=top_k,
        )

        # R4 — summarize (information firewall)
        result = await self.summarizer.summarize(chunks=chunks, raw_query=raw_query)

        logger.info(
            "RAGTrack: query=%s | chunks=%d | confidence=%.2f",
            raw_query[:60], result.chunk_count_used, result.confidence,
        )
        return result
