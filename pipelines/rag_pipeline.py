from __future__ import annotations
"""
RAG Pipeline — R1 through R4.

R1: Classify document types  (LLM, optional — skipped on timeout)
R2: Query embedding            (direct embedding — hybrid BM25 covers the lexical gap)
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

    # R2 — Embed query directly
    from infrastructure.embedding_service import get_embedder
    query_embedding = await get_embedder().embed(
        query, model=cfg.get("embedding_model", "nomic-embed-text")
    )
    logger.debug(f"[RAG/{dept_tag}] R2 embedding generated")

    # R3 — Hybrid search (doc_types from R1 boost matching-type chunks via BM25)
    chunks = await doc.hybrid_search(
        query_embedding=query_embedding,
        query_text=query,
        dept_tag=dept_tag,
        doc_type_filter=doc_types or None,
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
    confidence = await _estimate_confidence(chunks, nl_summary, cfg)

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
        if not isinstance(result, list):
            return []
        # Local models sometimes wrap tags in objects ([{"tag": "policy"}])
        # instead of plain strings — accept both, drop anything else.
        tags: list = []
        for item in result:
            if isinstance(item, str):
                tags.append(item)
            elif isinstance(item, dict):
                tags.extend(v for v in item.values() if isinstance(v, str))
        return tags[:3]
    except Exception:
        return []


async def _estimate_confidence(chunks, nl_summary: str, cfg: dict) -> float:
    if not chunks:
        return 0.1
    top_k        = cfg.get("top_k", 10)
    completeness = min(1.0, len(chunks) / top_k)
    richness     = min(1.0, len(nl_summary) / 500)
    faithfulness = await _score_faithfulness(nl_summary, chunks)
    return round(
        richness     * 0.30 +
        faithfulness * 0.50 +
        completeness * 0.20,
        3,
    )


async def _score_faithfulness(nl_summary: str, chunks) -> float:
    """
    LLM-as-judge: score how faithfully the NL summary reflects the source chunks.
    Uses a fast model with tight timeout so it never blocks the pipeline.
    Falls back to 0.65 (just below HIGH_CONF) on any failure.
    """
    try:
        context = "\n\n".join(c.text for c in chunks[:5])[:3000]
        llm = get_llm()
        system = (
            "You are a faithfulness evaluator. "
            "Score how faithfully this summary reflects the source documents. "
            "Return ONLY a single float between 0.0 and 1.0. "
            "1.0 = every claim in the summary is directly supported by the sources. "
            "0.0 = the summary contains claims not present in the sources."
        )
        result = await asyncio.wait_for(
            llm.complete(
                f"Summary:\n{nl_summary}\n\nSource documents:\n{context}",
                system=system,
            ),
            timeout=8.0,
        )
        score = float(result.strip().split()[0])
        return max(0.0, min(1.0, score))
    except Exception:
        return 0.65  # safe fallback — signals uncertain, not high-confidence
