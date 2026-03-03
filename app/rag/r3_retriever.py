"""
R3 — Chunk Retriever

Hybrid retrieval combining dense vector similarity (ChromaDB) with
sparse BM25 keyword matching. Uses RRF to merge results.

Extracts and passes ChunkResult objects to R4. Never returns raw chunks
to any component outside the RAG track.
"""

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional

from app.rag.r2_rewriter import RewriteResult
from app.services.vector_store import VectorStore
from app.services.full_text_search import FullTextSearchEngine

logger = logging.getLogger(__name__)


@dataclass
class ChunkResult:
    chunk_text: str
    doc_id: str
    filename: str
    chunk_id: int
    relevance_score: float       # normalized relevance (higher = better)
    doc_type: str = "narrative"
    page: Optional[int] = None
    section: Optional[str] = None


class ChunkRetriever:
    """
    R3 — retrieves relevant chunks via hybrid semantic + keyword search.
    Passes ChunkResult objects to R4 only.
    """

    def __init__(
        self,
        vector_store: VectorStore,
        bm25_engine: FullTextSearchEngine,
    ):
        self.vector_store = vector_store
        self.bm25 = bm25_engine

    async def retrieve(
        self,
        rewrite_result: RewriteResult,
        embedding_manager,
        top_k: int = 5,
        doc_type_filter: Optional[str] = None,
    ) -> List[ChunkResult]:
        """
        Retrieve top-K chunks using hybrid search.

        1. Embed rewritten query (or HyDE passage for semantic search)
        2. Vector search (semantic)
        3. BM25 search (keyword)
        4. Hybrid merge via RRF
        5. Return ChunkResult list
        """
        # Use HyDE passage for embedding if available (better recall)
        semantic_query_text = rewrite_result.hyde_passage or rewrite_result.rewritten_query

        try:
            query_embedding = embedding_manager.embed([semantic_query_text])[0]
        except Exception as e:
            logger.warning("R3 embedding failed: %s", e)
            return []

        # Vector search
        where_filter = {"doc_type": doc_type_filter} if doc_type_filter else None
        semantic_results = self.vector_store.search(
            query_embedding=query_embedding,
            top_k=top_k * 2,  # over-retrieve, then re-rank
            where_filter=where_filter,
        )

        # BM25 keyword search
        keyword_results = self.bm25.search_keyword(
            rewrite_result.rewritten_query, top_k=top_k * 2
        )

        # Hybrid merge
        merged = FullTextSearchEngine.hybrid_merge(
            semantic_results=semantic_results,
            keyword_results=keyword_results,
            alpha=0.6,
            top_k=top_k,
        )

        # Convert to ChunkResult objects
        chunk_results = []
        for item in merged:
            meta = item.get("metadata", {})
            text = item.get("document") or meta.get("chunk_text", "")
            if not text:
                continue

            # Normalize distance/score to relevance (higher = more relevant)
            raw_score = item.get("score", 1.0)
            relevance = 1.0 - min(raw_score, 1.0)  # lower distance = higher relevance

            chunk_results.append(ChunkResult(
                chunk_text=text,
                doc_id=meta.get("doc_id", ""),
                filename=meta.get("filename", meta.get("doc_id", "")),
                chunk_id=int(meta.get("chunk_id", 0)),
                relevance_score=relevance,
                doc_type=meta.get("doc_type", "narrative"),
                page=int(meta["page"]) if meta.get("page") else None,
                section=meta.get("section"),
            ))

        logger.info(
            "R3: retrieved %d chunks (semantic=%d, keyword=%d) for query: %s",
            len(chunk_results), len(semantic_results), len(keyword_results),
            rewrite_result.rewritten_query[:60],
        )
        return chunk_results
