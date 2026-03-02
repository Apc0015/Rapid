"""
Speculative RAG Pipeline for Intelligent Auto-RAG.

Implements the Speculative RAG pattern:
  1. DRAFT: A fast/small LLM generates a candidate answer from retrieved context
  2. VERIFY: The main (larger) LLM verifies the draft's faithfulness and fills gaps
  3. MERGE: If draft is verified → use it (fast); else → use the verifier's answer

Benefits:
  - Reduces latency: small LLM draft is fast; verifier only fixes errors
  - Higher faithfulness: verification step catches hallucinations
  - Cost-efficient: many queries pass verification after small model draft

Configuration (via env vars):
  SPECULATIVE_DRAFT_MODEL  — provider:model for the draft LLM (e.g. "openai:gpt-3.5-turbo")
  SPECULATIVE_VERIFY_MODEL — provider:model for the verifier LLM (e.g. "openai:gpt-4o")
  SPECULATIVE_THRESHOLD    — faithfulness score above which the draft is accepted (default: 0.70)
"""

import os
import re
import logging
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)

_DEFAULT_THRESHOLD = float(os.getenv("SPECULATIVE_THRESHOLD", "0.70"))


class SpeculativePipeline:
    """
    Speculative RAG: draft → verify → merge.

    Usage:
        pipeline = SpeculativePipeline(draft_llm, verify_llm)
        result = pipeline.run(question, chunks)
        print(result["answer"])         # Final answer
        print(result["used_draft"])     # True if draft was accepted
    """

    def __init__(
        self,
        draft_llm: Any,
        verify_llm: Optional[Any] = None,
        threshold: float = _DEFAULT_THRESHOLD,
    ):
        """
        Args:
            draft_llm: Fast/small LLM for drafting. Can be same as verify_llm.
            verify_llm: Larger/slower LLM for verification. Defaults to draft_llm.
            threshold: Faithfulness score above which draft is accepted (0.0–1.0).
        """
        self.draft_llm = draft_llm
        self.verify_llm = verify_llm or draft_llm
        self.threshold = threshold

    def run(
        self,
        question: str,
        chunks: List[str],
        chunk_sources: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Execute the speculative pipeline.

        Args:
            question: User question.
            chunks: Retrieved context chunks.
            chunk_sources: Optional filenames for citation tracking.

        Returns:
            {
                answer: str,
                used_draft: bool,
                draft_score: float,
                draft_answer: str,
                verification_notes: str,
            }
        """
        if not chunks:
            return {
                "answer": "No context retrieved — cannot answer.",
                "used_draft": False,
                "draft_score": 0.0,
                "draft_answer": "",
                "verification_notes": "No chunks",
            }

        # ── Step 1: Draft ─────────────────────────────────────────────────
        draft_answer = self._draft(question, chunks)
        logger.debug("Speculative draft: %s", draft_answer[:100])

        # ── Step 2: Score draft faithfulness ──────────────────────────────
        from app.services.confidence_scorer import ConfidenceScorer
        scorer = ConfidenceScorer()
        citation_result = scorer.score_citation_faithfulness(
            draft_answer, chunks, chunk_sources
        )
        draft_score = citation_result["supported_fraction"]

        # ── Step 3: Accept or verify ──────────────────────────────────────
        if draft_score >= self.threshold:
            logger.info(
                "Speculative: draft accepted (score=%.2f ≥ threshold=%.2f)",
                draft_score, self.threshold,
            )
            return {
                "answer": draft_answer,
                "used_draft": True,
                "draft_score": draft_score,
                "draft_answer": draft_answer,
                "verification_notes": "Draft accepted — no verification needed",
            }

        # Draft score below threshold → verify and potentially fix
        logger.info(
            "Speculative: draft score=%.2f below threshold=%.2f — verifying",
            draft_score, self.threshold,
        )
        verified_answer, notes = self._verify(
            question, chunks, draft_answer,
            unsupported=citation_result.get("unsupported_sentences", []),
        )

        return {
            "answer": verified_answer,
            "used_draft": False,
            "draft_score": draft_score,
            "draft_answer": draft_answer,
            "verification_notes": notes,
        }

    def stream(
        self,
        question: str,
        chunks: List[str],
    ):
        """
        Streaming version: draft synchronously, then stream verification.
        Yields tokens. Draft is used directly if score ≥ threshold.
        """
        if not chunks:
            yield "No context retrieved — cannot answer."
            return

        # Draft (non-streaming, fast)
        draft_answer = self._draft(question, chunks)

        from app.services.confidence_scorer import ConfidenceScorer
        scorer = ConfidenceScorer()
        citation_result = scorer.score_citation_faithfulness(draft_answer, chunks)
        draft_score = citation_result["supported_fraction"]

        if draft_score >= self.threshold:
            yield draft_answer
            return

        # Verification pass with streaming
        yield from self._stream_verify(question, chunks, draft_answer)

    # ── Private methods ───────────────────────────────────────────────────────

    def _draft(self, question: str, chunks: List[str]) -> str:
        """Generate a fast draft answer using the draft LLM."""
        context = "\n---\n".join(chunks[:5])  # Use top 5 chunks for speed
        prompt = (
            f"Answer the following question using ONLY the provided context.\n"
            f"Be concise. If you cannot answer from the context, say 'I cannot answer this from the context.'\n\n"
            f"Context:\n{context}\n\n"
            f"Question: {question}\n\n"
            f"Answer:"
        )
        from langchain_core.messages import HumanMessage
        try:
            response = self.draft_llm.invoke([HumanMessage(content=prompt)])
            return response.content.strip()
        except Exception as e:
            logger.warning("Draft LLM failed: %s", e)
            return "Draft generation failed."

    def _verify(
        self,
        question: str,
        chunks: List[str],
        draft: str,
        unsupported: Optional[List[str]] = None,
    ) -> tuple:
        """
        Verify and improve the draft answer using the verification LLM.

        Returns (verified_answer, notes).
        """
        context = "\n---\n".join(chunks)
        unsupported_text = ""
        if unsupported:
            unsupported_text = (
                "\n\nThe following draft sentences may be unsupported by the context — "
                "please correct or remove them:\n"
                + "\n".join(f"- {s}" for s in unsupported[:5])
            )

        prompt = (
            f"You are verifying a draft answer for factual accuracy against the provided context.\n\n"
            f"Context:\n{context}\n\n"
            f"Question: {question}\n\n"
            f"Draft answer:\n{draft}"
            f"{unsupported_text}\n\n"
            f"Instructions:\n"
            f"1. Keep the draft if it is well-supported by the context.\n"
            f"2. Correct any unsupported claims using only the context above.\n"
            f"3. If the draft is mostly wrong, write a new answer from scratch.\n"
            f"4. Keep the final answer concise and complete.\n\n"
            f"Verified answer:"
        )
        from langchain_core.messages import HumanMessage
        try:
            response = self.verify_llm.invoke([HumanMessage(content=prompt)])
            verified = response.content.strip()
            notes = f"Verified: {len(unsupported or [])} unsupported sentences corrected"
            return verified, notes
        except Exception as e:
            logger.warning("Verify LLM failed: %s", e)
            return draft, f"Verification failed: {e}"

    def _stream_verify(self, question: str, chunks: List[str], draft: str):
        """Stream the verification response."""
        context = "\n---\n".join(chunks)
        prompt = (
            f"Context:\n{context}\n\n"
            f"Question: {question}\n\n"
            f"Draft answer: {draft}\n\n"
            f"Verify and improve the draft using only the context. Final answer:"
        )
        from langchain_core.messages import HumanMessage
        try:
            for chunk in self.verify_llm.stream([HumanMessage(content=prompt)]):
                token = getattr(chunk, "content", "")
                if token:
                    yield token
        except Exception as e:
            logger.warning("Stream verification failed: %s — using draft", e)
            yield draft


def build_speculative_pipeline(
    rag_engine: Any,
    draft_model: Optional[str] = None,
    verify_model: Optional[str] = None,
) -> SpeculativePipeline:
    """
    Factory: build a SpeculativePipeline from a RAGEngine instance.

    Uses the same LLM client for both draft and verify if only one is available.
    Pass SPECULATIVE_DRAFT_MODEL and SPECULATIVE_VERIFY_MODEL env vars to use
    different models.

    Args:
        rag_engine: RAGEngine instance (for LLM access).
        draft_model: Optional override — "openai:gpt-3.5-turbo" etc.
        verify_model: Optional override — "openai:gpt-4o" etc.
    """
    draft_model = draft_model or os.getenv("SPECULATIVE_DRAFT_MODEL")
    verify_model = verify_model or os.getenv("SPECULATIVE_VERIFY_MODEL")

    # Build draft LLM
    draft_llm = _get_llm(rag_engine, draft_model)
    # Build verify LLM (may be same as draft)
    verify_llm = _get_llm(rag_engine, verify_model) if verify_model else draft_llm

    return SpeculativePipeline(draft_llm, verify_llm)


def _get_llm(rag_engine: Any, model_spec: Optional[str]) -> Any:
    """Get LLM client from engine or from a model spec string."""
    if model_spec:
        try:
            provider, model = model_spec.split(":", 1)
            llm = rag_engine.llm_manager.get_langchain_llm(provider, model)
            if llm:
                return llm
        except Exception as e:
            logger.debug("Could not build LLM from spec '%s': %s", model_spec, e)
    return rag_engine._get_llm_client()
