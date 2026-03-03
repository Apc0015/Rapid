"""
R4 — NL Summarizer (RAG Information Firewall)

Converts retrieved chunks into a single NL paragraph.
This is the information firewall of the RAG track.

CRITICAL: raw chunk text never leaves this module.
RAGSummaryResult has no `chunks` or `chunk_text` field — structural enforcement.
"""

import logging
from dataclasses import dataclass, field
from typing import List, Optional

from app.rag.r3_retriever import ChunkResult
from app.services.llm_service import LLMManager

logger = logging.getLogger(__name__)


@dataclass
class RAGSourceCitation:
    filename: str
    doc_id: str
    chunk_id: int
    page: Optional[int]
    section: Optional[str]
    relevance_score: float


@dataclass
class RAGSummaryResult:
    nl_summary: str                         # NL paragraph — the ONLY output
    sources: List[RAGSourceCitation]        # citation metadata (no raw text)
    confidence: float
    chunk_count_used: int
    # NOTE: chunks and chunk_text are intentionally NOT stored here.
    # This is a structural privacy enforcement — raw chunks are consumed
    # here and not placed in any return field.


class NLSummarizer:
    """
    R4 — information firewall of the RAG track.

    Converts raw chunks to NL paragraph. Chunks are consumed here.
    Raw text never appears in the return value.
    """

    def __init__(self, llm_manager: LLMManager):
        self.llm = llm_manager

    async def summarize(
        self,
        chunks: List[ChunkResult],
        raw_query: str,
    ) -> RAGSummaryResult:
        """
        Produce a focused NL paragraph from retrieved chunks.

        THE FIREWALL: chunk_text is used internally to build the LLM prompt,
        then discarded. It is never stored in the return value.
        """
        if not chunks:
            return RAGSummaryResult(
                nl_summary="No relevant information was found in the documents for this question.",
                sources=[],
                confidence=0.0,
                chunk_count_used=0,
            )

        # Sort by relevance, use top chunks
        sorted_chunks = sorted(chunks, key=lambda c: c.relevance_score, reverse=True)
        top_chunks = sorted_chunks[:6]  # cap at 6 chunks for LLM context

        # Build context string (internal use only — never returned)
        context_parts = []
        for i, chunk in enumerate(top_chunks, 1):
            context_parts.append(f"[Excerpt {i} from {chunk.filename}]\n{chunk.chunk_text}")
        context_text = "\n\n".join(context_parts)

        prompt = f"""Answer the following question using ONLY the document excerpts provided below.

Question: {raw_query}

Document excerpts:
{context_text}

Rules:
- Write a concise, focused natural language paragraph (3-6 sentences)
- Answer the specific question asked — do not summarize the documents generally
- Preserve exact figures, names, and dates found in the excerpts
- Do not copy long verbatim passages — synthesize and explain
- If the excerpts do not contain enough information to answer, say so clearly
- Do not mention "according to the excerpt" or similar phrases — write naturally"""

        try:
            nl_summary = await self.llm.chat(prompt, max_tokens=600, temperature=0.0)
        except Exception as e:
            logger.error("R4 summarization failed: %s", e)
            nl_summary = "The documents were retrieved but could not be summarized due to a technical error."

        # Build source citations from metadata only — no raw text
        sources = [
            RAGSourceCitation(
                filename=chunk.filename,
                doc_id=chunk.doc_id,
                chunk_id=chunk.chunk_id,
                page=chunk.page,
                section=chunk.section,
                relevance_score=round(chunk.relevance_score, 3),
            )
            for chunk in top_chunks
        ]

        # Confidence: average of top chunk relevance scores
        avg_relevance = sum(c.relevance_score for c in top_chunks) / len(top_chunks)
        confidence = min(avg_relevance * 1.2, 1.0)  # slight boost for having chunks

        # Check if we got an "I don't know" style answer
        refusal_phrases = ["do not contain", "cannot answer", "no information", "not found"]
        if any(p in nl_summary.lower() for p in refusal_phrases):
            confidence = min(confidence, 0.35)

        logger.info(
            "R4: summarized %d chunks → confidence=%.2f, query=%s",
            len(top_chunks), confidence, raw_query[:60],
        )

        # Chunk text is NOT placed in the return value — structural firewall
        return RAGSummaryResult(
            nl_summary=nl_summary,
            sources=sources,
            confidence=confidence,
            chunk_count_used=len(top_chunks),
        )
