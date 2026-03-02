"""
Confidence Scorer for Intelligent Auto-RAG.

After retrieval and generation, scores the answer on three dimensions:
  1. Context Relevance  — are the retrieved chunks actually about the question?
  2. Faithfulness       — is the answer grounded in the retrieved context?
  3. Completeness       — did the answer address what was asked?

Combined score drives retry logic:
  - HIGH (≥ 0.65) → return answer
  - MEDIUM (0.40–0.65) → return with low-confidence flag
  - LOW (< 0.40) → retry with different strategy
"""

import re
import logging
from dataclasses import dataclass
from typing import List, Optional, Any, Dict

logger = logging.getLogger(__name__)

# Thresholds
HIGH_CONFIDENCE = 0.65
LOW_CONFIDENCE = 0.40

# Common stop words excluded from keyword overlap scoring
_STOP_WORDS = {
    "what", "how", "who", "when", "where", "why", "which", "is", "are",
    "was", "were", "the", "a", "an", "and", "or", "but", "in", "on",
    "at", "to", "for", "of", "with", "by", "from", "about", "does",
    "do", "did", "can", "could", "should", "would", "will", "has", "have",
    "had", "be", "been", "being", "this", "that", "these", "those", "it",
}


@dataclass
class ConfidenceResult:
    """Structured result from confidence scoring."""
    context_relevance: float   # 0.0 – 1.0
    faithfulness: float        # 0.0 – 1.0
    completeness: float        # 0.0 – 1.0
    overall: float             # weighted average
    verdict: str               # "high" | "medium" | "low"
    # Retry recommendation
    retry_reason: Optional[str]       # what failed ("retrieval" | "faithfulness" | "completeness" | None)
    retry_suggestion: Optional[str]   # what to try next
    unanswerable: bool = False        # True if query appears unanswerable from context
    conflicts: List[tuple] = None     # List of (i, j, reason) conflict tuples

    def __post_init__(self):
        if self.conflicts is None:
            self.conflicts = []

    def passed(self) -> bool:
        return self.overall >= HIGH_CONFIDENCE

    def should_retry(self) -> bool:
        return self.overall < LOW_CONFIDENCE


class ConfidenceScorer:
    """
    Scores retrieval + generation quality for a query-answer pair.

    Heuristic-first for speed. Optional LLM faithfulness check
    (one lightweight call) for higher accuracy when needed.
    """

    def score(
        self,
        query: str,
        chunks: List[str],
        answer: str,
        llm_client: Optional[Any] = None,
        use_llm_faithfulness: bool = True,
    ) -> ConfidenceResult:
        """
        Score the quality of a retrieval + generation cycle.

        Args:
            query: The original user question.
            chunks: Retrieved document chunks used as context.
            answer: The LLM-generated answer.
            llm_client: Optional LangChain LLM client for faithfulness check.
            use_llm_faithfulness: If True and llm_client provided, use LLM scoring.

        Returns:
            ConfidenceResult with scores and retry recommendation.
        """
        if not chunks:
            return ConfidenceResult(
                context_relevance=0.0,
                faithfulness=0.0,
                completeness=0.0,
                overall=0.0,
                verdict="low",
                retry_reason="retrieval",
                retry_suggestion="No chunks retrieved — try broader search or different source",
            )

        # 1. Context relevance (heuristic — fast)
        cr = self._score_context_relevance(query, chunks)

        # 2. Faithfulness (LLM if available, else heuristic)
        if llm_client is not None and use_llm_faithfulness:
            fa = self._score_faithfulness_llm(query, chunks, answer, llm_client)
        else:
            fa = self._score_faithfulness_heuristic(answer, chunks)

        # 3. Completeness (heuristic — fast)
        co = self._score_completeness(query, answer)

        # Weighted average: faithfulness matters most
        overall = (cr * 0.30) + (fa * 0.50) + (co * 0.20)

        verdict = (
            "high" if overall >= HIGH_CONFIDENCE else
            "medium" if overall >= LOW_CONFIDENCE else
            "low"
        )

        retry_reason, retry_suggestion = self._get_retry_recommendation(cr, fa, co)

        # 4. Unanswerable detection
        unanswerable = self.is_unanswerable(query, chunks)
        if unanswerable and overall > LOW_CONFIDENCE:
            # Penalise — context may be retrieved but doesn't address the query
            overall = min(overall, LOW_CONFIDENCE - 0.01)
            verdict = "low"
            retry_reason = retry_reason or "retrieval"
            retry_suggestion = retry_suggestion or "Query unanswerable from current context — try web search or broader sources"

        # 5. Conflict detection
        conflicts = self.detect_conflicts(chunks)
        if conflicts:
            logger.warning("ConfidenceScorer: %d conflict(s) detected in chunks", len(conflicts))

        logger.info(
            "ConfidenceScorer: cr=%.2f fa=%.2f co=%.2f → overall=%.2f (%s) unanswerable=%s conflicts=%d",
            cr, fa, co, overall, verdict, unanswerable, len(conflicts),
        )

        return ConfidenceResult(
            context_relevance=cr,
            faithfulness=fa,
            completeness=co,
            overall=overall,
            verdict=verdict,
            retry_reason=retry_reason,
            retry_suggestion=retry_suggestion,
            unanswerable=unanswerable,
            conflicts=conflicts,
        )

    # ─── Context Relevance ────────────────────────────────────────────────────

    def _score_context_relevance(self, query: str, chunks: List[str]) -> float:
        """
        Keyword overlap between query terms and retrieved chunks.
        Higher overlap → chunks are more relevant to the query.
        """
        query_words = self._extract_keywords(query)
        if not query_words:
            return 0.7  # can't score without query keywords → assume ok

        chunk_scores = []
        for chunk in chunks:
            chunk_words = set(chunk.lower().split())
            overlap = len(query_words & chunk_words) / len(query_words)
            chunk_scores.append(overlap)

        # Take average of top-3 chunks (best chunks matter most)
        top_scores = sorted(chunk_scores, reverse=True)[:3]
        raw = sum(top_scores) / len(top_scores)

        # Scale: even 0.3 raw overlap is reasonably relevant
        return min(raw * 2.5, 1.0)

    # ─── Faithfulness ─────────────────────────────────────────────────────────

    def _score_faithfulness_llm(
        self,
        query: str,
        chunks: List[str],
        answer: str,
        llm_client: Any,
    ) -> float:
        """
        Ask the LLM: is the answer grounded in the context?
        Single lightweight call — returns a 0–10 number.
        """
        # Use only top 3 chunks to keep the prompt short
        context_sample = "\n---\n".join(chunks[:3])
        prompt = (
            "You are evaluating a RAG system's answer quality.\n\n"
            f"Context retrieved:\n{context_sample}\n\n"
            f"Question: {query}\n\n"
            f"Answer given: {answer}\n\n"
            "Rate how well the answer is supported by the context above.\n"
            "Reply with ONLY a single integer from 0 to 10:\n"
            "10 = completely supported by context\n"
            "5  = partially supported, some unsupported claims\n"
            "0  = not supported, answer seems hallucinated\n\n"
            "Score:"
        )
        try:
            from langchain_core.messages import HumanMessage
            response = llm_client.invoke([HumanMessage(content=prompt)])
            raw_text = response.content.strip()
            # Extract first number found
            numbers = re.findall(r"\d+", raw_text)
            if numbers:
                score = int(numbers[0])
                return min(max(score / 10.0, 0.0), 1.0)
        except Exception as e:
            logger.warning("LLM faithfulness check failed: %s", e)

        # Fallback to heuristic
        return self._score_faithfulness_heuristic(answer, chunks)

    def _score_faithfulness_heuristic(self, answer: str, chunks: List[str]) -> float:
        """
        Heuristic faithfulness: what fraction of answer's key terms
        appear in the retrieved context?
        """
        answer_keywords = self._extract_keywords(answer)
        if not answer_keywords:
            return 0.7

        all_chunk_text = " ".join(chunks).lower()
        found = sum(1 for kw in answer_keywords if kw in all_chunk_text)
        return found / len(answer_keywords)

    # ─── Completeness ─────────────────────────────────────────────────────────

    def _score_completeness(self, query: str, answer: str) -> float:
        """
        Heuristic: did the answer substantively address the question?
        Checks answer length and keyword coverage of query intent.
        """
        answer_words = answer.split()

        # Too short = incomplete
        if len(answer_words) < 8:
            return 0.2

        # "I don't know" type answers = low completeness
        evasion_phrases = [
            "i don't have", "i cannot", "i do not have", "no information",
            "not found", "no accessible", "unable to", "i'm not sure",
        ]
        answer_lower = answer.lower()
        if any(p in answer_lower for p in evasion_phrases):
            return 0.25

        # Keyword coverage: does the answer address the query's key terms?
        query_keywords = self._extract_keywords(query)
        if not query_keywords:
            # No query keywords to check → score by length alone
            return min(len(answer_words) / 50.0, 1.0)

        answer_text = answer_lower
        covered = sum(1 for kw in query_keywords if kw in answer_text)
        coverage = covered / len(query_keywords)

        # Bonus for longer, more detailed answers
        length_bonus = min(len(answer_words) / 100.0, 0.2)
        return min(coverage + length_bonus, 1.0)

    # ─── Unanswerable detection ────────────────────────────────────────────────

    @staticmethod
    def is_unanswerable(query: str, chunks: List[str]) -> bool:
        """
        Detect whether the query is likely unanswerable from the given context.

        Returns True if the retrieved chunks contain no keywords related to the query.
        """
        query_keywords = set(re.findall(r"\b[a-zA-Z]{3,}\b", query.lower())) - _STOP_WORDS
        if not query_keywords:
            return False

        all_chunk_text = " ".join(chunks).lower()
        # If fewer than 20% of query keywords appear in ANY chunk → unanswerable
        found = sum(1 for kw in query_keywords if kw in all_chunk_text)
        coverage = found / len(query_keywords)
        return coverage < 0.20

    # ─── Conflict detection ────────────────────────────────────────────────────

    @staticmethod
    def detect_conflicts(chunks: List[str]) -> List[tuple]:
        """
        Detect potential factual conflicts across retrieved chunks.

        Uses simple heuristic: look for contradictory number patterns or
        negation patterns that differ across chunks.

        Returns list of (chunk_i_idx, chunk_j_idx, reason) tuples.
        """
        conflicts = []
        if len(chunks) < 2:
            return conflicts

        # Numeric conflict detection: same noun near different numbers
        num_pattern = re.compile(r"(\b[\w]+\b)\s+(?:is|are|was|were|has|=)\s+([\d,\.]+)")

        fact_maps = []
        for chunk in chunks:
            facts: dict = {}
            for match in num_pattern.finditer(chunk.lower()):
                subject = match.group(1)
                value = match.group(2).replace(",", "")
                facts[subject] = value
            fact_maps.append(facts)

        for i in range(len(chunks)):
            for j in range(i + 1, len(chunks)):
                for subject, val_i in fact_maps[i].items():
                    val_j = fact_maps[j].get(subject)
                    if val_j and val_j != val_i:
                        try:
                            # Only flag if both are numeric and differ
                            if float(val_i) != float(val_j):
                                conflicts.append(
                                    (i, j, f"Conflict on '{subject}': {val_i} vs {val_j}")
                                )
                        except ValueError:
                            pass

        return conflicts[:5]  # Cap at 5 conflicts to avoid noise

    # ─── Citation-level faithfulness ──────────────────────────────────────────

    def score_citation_faithfulness(
        self,
        answer: str,
        chunks: List[str],
        chunk_sources: Optional[List[str]] = None,
    ) -> dict:
        """
        Citation-level faithfulness: for each sentence in the answer,
        find the supporting chunk (if any).

        Returns a dict:
            {
              "sentence_scores": [{"sentence": ..., "supported": bool, "source_chunk_idx": int|None}],
              "supported_fraction": float,
              "unsupported_sentences": [str],
            }
        """
        sentences = re.split(r"(?<=[.!?])\s+", answer.strip())
        sentences = [s.strip() for s in sentences if len(s.split()) >= 4]

        sentence_scores = []
        unsupported = []

        for sent in sentences:
            sent_kws = self._extract_keywords(sent)
            if not sent_kws:
                sentence_scores.append({
                    "sentence": sent, "supported": True, "source_chunk_idx": None
                })
                continue

            best_idx = None
            best_overlap = 0.0
            for ci, chunk in enumerate(chunks):
                chunk_kws = self._extract_keywords(chunk)
                if not chunk_kws:
                    continue
                overlap = len(sent_kws & chunk_kws) / len(sent_kws)
                if overlap > best_overlap:
                    best_overlap = overlap
                    best_idx = ci

            supported = best_overlap >= 0.30  # ≥30% keyword coverage = supported
            if not supported:
                unsupported.append(sent)

            entry: dict = {
                "sentence": sent, "supported": supported, "source_chunk_idx": best_idx
            }
            if chunk_sources and best_idx is not None and best_idx < len(chunk_sources):
                entry["source"] = chunk_sources[best_idx]
            sentence_scores.append(entry)

        supported_count = sum(1 for s in sentence_scores if s["supported"])
        supported_fraction = (
            supported_count / len(sentence_scores) if sentence_scores else 1.0
        )

        return {
            "sentence_scores": sentence_scores,
            "supported_fraction": round(supported_fraction, 3),
            "unsupported_sentences": unsupported,
        }

    # ─── Retry recommendation ─────────────────────────────────────────────────

    @staticmethod
    def _get_retry_recommendation(
        cr: float, fa: float, co: float
    ):
        """Determine what failed and what to try next."""
        if cr < 0.30:
            return (
                "retrieval",
                "Context not relevant — retry with different search mode or expand sources",
            )
        if fa < 0.40:
            return (
                "faithfulness",
                "Answer not grounded — increase top_k to provide more context to LLM",
            )
        if co < 0.35:
            return (
                "completeness",
                "Answer incomplete — try web search or broader retrieval",
            )
        return None, None

    # ─── Helpers ──────────────────────────────────────────────────────────────

    @staticmethod
    def _extract_keywords(text: str) -> set:
        """Extract meaningful keywords from text (removes stop words)."""
        words = re.findall(r"\b[a-zA-Z]{3,}\b", text.lower())
        return {w for w in words if w not in _STOP_WORDS}
