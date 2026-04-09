from __future__ import annotations
"""
RAG Pipeline — R1 through R4.

R1: Classify document types  (LLM, optional — skipped on timeout)
R2: HyDE query rewriting      (embed hypothetical answer, not the question)
R3: Hybrid retrieval          (FAISS vector + BM25 → Reciprocal Rank Fusion)
R4: NL summarisation          (RAG firewall — raw chunks never leave this pipeline)

Each department uses its own FAISS index and RAG config.
"""

import asyncio
import logging
from models.nl_result import NLResult
from infrastructure.doc_master import get_doc_master
from infrastructure.dept_config import get_dept_config
from infrastructure.llm_client import get_llm

logger = logging.getLogger(__name__)


async def run_rag_pipeline(query: str, dept_tag: str, user_permissions: dict) -> NLResult:
    """Full RAG pipeline. Returns NLResult with NL summary + citations."""
    doc = get_doc_master()
    cfg = get_dept_config().get_rag(dept_tag)

    # R1 — Classify document types (best-effort, non-blocking)
    doc_types = await _classify_doc_types_safe(query, dept_tag)
    logger.debug(f"[RAG/{dept_tag}] R1 doc types: {doc_types}")

    # R2 — HyDE: embed hypothetical answer in dept context
    if cfg.get("hyde_enabled", True):
        query_embedding = await doc.rewrite_query_hyde(query, dept_tag=dept_tag)
    else:
        from infrastructure.embedding_service import get_embedder
        query_embedding = await get_embedder().embed(
            query, model=cfg.get("embedding_model", "nomic-embed-text")
        )
    logger.debug(f"[RAG/{dept_tag}] R2 embedding generated")

    # R3 — Hybrid search against dept's own FAISS index
    chunks = await doc.hybrid_search(
        query_embedding=query_embedding,
        query_text=query,
        dept_tag=dept_tag,
    )
    logger.debug(f"[RAG/{dept_tag}] R3 retrieved {len(chunks)} chunks")

    if not chunks:
        return NLResult(
            summary=(
                f"No relevant documents were found in the {dept_tag.upper()} "
                "knowledge base for this query."
            ),
            source="rag",
            confidence=0.1,
            dept_tag=dept_tag,
        )

    # R4 — Convert to NL (RAG firewall — chunks consumed here)
    nl_summary, citations = await doc.convert_chunks_to_nl(
        chunks, query, dept_tag=dept_tag
    )
    confidence = _estimate_confidence(chunks, nl_summary, cfg)

    return NLResult(
        summary=nl_summary,
        source="rag",
        confidence=confidence,
        citations=citations,
        dept_tag=dept_tag,
    )


async def _classify_doc_types_safe(query: str, dept_tag: str) -> list:
    """R1: Tag query with document categories. Non-blocking — returns [] on any failure."""
    try:
        llm = get_llm()
        system = (
            f"Classify this enterprise query into document categories for the {dept_tag} department. "
            "Return a JSON array of up to 3 tags from: "
            "[policy, handbook, report, contract, procedure, regulation, guide, template, form]. "
            "Return ONLY the JSON array."
        )
        result = await asyncio.wait_for(
            llm.json_complete(query, system=system),
            timeout=8.0,
        )
        return result if isinstance(result, list) else []
    except Exception:
        return []


def _estimate_confidence(chunks, nl_summary: str, cfg: dict) -> float:
    if not chunks:
        return 0.1
    top_k       = cfg.get("top_k", 10)
    completeness = min(1.0, len(chunks) / top_k)
    richness     = min(1.0, len(nl_summary) / 500)
    faithfulness = 0.7   # conservative estimate without a verifier
    return round(
        richness     * 0.30 +
        faithfulness * 0.50 +
        completeness * 0.20,
        3,
    )
