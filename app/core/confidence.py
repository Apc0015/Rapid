"""
Confidence Scorer — adapted from the original confidence_scorer.py.

Changes from original:
- `chunks` parameter renamed to `summaries` (operates on NL summaries, not raw chunks)
- LLM faithfulness check uses LLMManager.chat() instead of LangChain
- score() is now async
- LangChain import removed
"""

import re
import logging
from dataclasses import dataclass
from typing import List, Optional, Any

logger = logging.getLogger(__name__)

HIGH_CONFIDENCE = 0.65
LOW_CONFIDENCE = 0.40

_STOP_WORDS = {
    "what", "how", "who", "when", "where", "why", "which", "is", "are",
    "was", "were", "the", "a", "an", "and", "or", "but", "in", "on",
    "at", "to", "for", "of", "with", "by", "from", "about", "does",
    "do", "did", "can", "could", "should", "would", "will", "has", "have",
    "had", "be", "been", "being", "this", "that", "these", "those", "it",
}


@dataclass
class ConfidenceResult:
    context_relevance: float
    faithfulness: float
    completeness: float
    overall: float
    verdict: str               # "high" | "medium" | "low"
    retry_reason: Optional[str]
    retry_suggestion: Optional[str]
    unanswerable: bool = False
    conflicts: List[tuple] = None

    def __post_init__(self):
        if self.conflicts is None:
            self.conflicts = []

    def passed(self) -> bool:
        return self.overall >= HIGH_CONFIDENCE

    def should_retry(self) -> bool:
        return self.overall < LOW_CONFIDENCE


class ConfidenceScorer:
    """
    Scores retrieval + generation quality.
    Operates on NL summaries (not raw chunks) in the new architecture.
    """

    async def score(
        self,
        query: str,
        summaries: List[str],       # NL summaries from R4/D5 (not raw chunks)
        answer: str,
        llm_manager=None,
        use_llm_faithfulness: bool = True,
    ) -> ConfidenceResult:
        if not summaries:
            return ConfidenceResult(
                context_relevance=0.0, faithfulness=0.0, completeness=0.0,
                overall=0.0, verdict="low",
                retry_reason="retrieval",
                retry_suggestion="No summaries available — check data sources",
            )

        cr = self._score_context_relevance(query, summaries)

        if llm_manager is not None and use_llm_faithfulness:
            fa = await self._score_faithfulness_llm(query, summaries, answer, llm_manager)
        else:
            fa = self._score_faithfulness_heuristic(answer, summaries)

        co = self._score_completeness(query, answer)
        overall = (cr * 0.30) + (fa * 0.50) + (co * 0.20)

        verdict = (
            "high" if overall >= HIGH_CONFIDENCE else
            "medium" if overall >= LOW_CONFIDENCE else
            "low"
        )
        retry_reason, retry_suggestion = self._get_retry_recommendation(cr, fa, co)

        unanswerable = self.is_unanswerable(query, summaries)
        if unanswerable and overall > LOW_CONFIDENCE:
            overall = min(overall, LOW_CONFIDENCE - 0.01)
            verdict = "low"
            retry_reason = retry_reason or "retrieval"
            retry_suggestion = retry_suggestion or "Query unanswerable — try web search"

        conflicts = self.detect_conflicts(summaries)
        if conflicts:
            logger.warning("ConfidenceScorer: %d conflict(s) in summaries", len(conflicts))

        logger.info(
            "Confidence: cr=%.2f fa=%.2f co=%.2f → %.2f (%s)",
            cr, fa, co, overall, verdict,
        )
        return ConfidenceResult(
            context_relevance=cr, faithfulness=fa, completeness=co,
            overall=overall, verdict=verdict,
            retry_reason=retry_reason, retry_suggestion=retry_suggestion,
            unanswerable=unanswerable, conflicts=conflicts,
        )

    def _score_context_relevance(self, query: str, summaries: List[str]) -> float:
        query_words = self._extract_keywords(query)
        if not query_words:
            return 0.7
        scores = []
        for s in summaries:
            s_words = set(s.lower().split())
            scores.append(len(query_words & s_words) / len(query_words))
        top = sorted(scores, reverse=True)[:3]
        return min(sum(top) / len(top) * 2.5, 1.0)

    async def _score_faithfulness_llm(
        self, query: str, summaries: List[str], answer: str, llm_manager
    ) -> float:
        context_sample = "\n---\n".join(summaries[:3])
        prompt = (
            f"Context:\n{context_sample}\n\n"
            f"Question: {query}\n\n"
            f"Answer: {answer}\n\n"
            "Rate how well the answer is supported by the context (0-10). "
            "Reply with ONLY a single integer. Score:"
        )
        try:
            raw = await llm_manager.chat(prompt, max_tokens=10, temperature=0.0)
            numbers = re.findall(r"\d+", raw)
            if numbers:
                return min(max(int(numbers[0]) / 10.0, 0.0), 1.0)
        except Exception as e:
            logger.warning("LLM faithfulness check failed: %s", e)
        return self._score_faithfulness_heuristic(answer, summaries)

    def _score_faithfulness_heuristic(self, answer: str, summaries: List[str]) -> float:
        answer_kws = self._extract_keywords(answer)
        if not answer_kws:
            return 0.7
        all_text = " ".join(summaries).lower()
        found = sum(1 for kw in answer_kws if kw in all_text)
        return found / len(answer_kws)

    def _score_completeness(self, query: str, answer: str) -> float:
        words = answer.split()
        if len(words) < 8:
            return 0.2
        evasions = [
            "i don't have", "i cannot", "i do not have", "no information",
            "not found", "unable to", "i'm not sure",
        ]
        if any(p in answer.lower() for p in evasions):
            return 0.25
        kws = self._extract_keywords(query)
        if not kws:
            return min(len(words) / 50.0, 1.0)
        covered = sum(1 for kw in kws if kw in answer.lower())
        length_bonus = min(len(words) / 100.0, 0.2)
        return min(covered / len(kws) + length_bonus, 1.0)

    @staticmethod
    def is_unanswerable(query: str, summaries: List[str]) -> bool:
        kws = set(re.findall(r"\b[a-zA-Z]{3,}\b", query.lower())) - _STOP_WORDS
        if not kws:
            return False
        all_text = " ".join(summaries).lower()
        found = sum(1 for kw in kws if kw in all_text)
        return (found / len(kws)) < 0.20

    @staticmethod
    def detect_conflicts(summaries: List[str]) -> List[tuple]:
        conflicts = []
        if len(summaries) < 2:
            return conflicts
        num_pattern = re.compile(r"(\b[\w]+\b)\s+(?:is|are|was|were|has|=)\s+([\d,\.]+)")
        fact_maps = []
        for s in summaries:
            facts: dict = {}
            for m in num_pattern.finditer(s.lower()):
                facts[m.group(1)] = m.group(2).replace(",", "")
            fact_maps.append(facts)
        for i in range(len(summaries)):
            for j in range(i + 1, len(summaries)):
                for subj, val_i in fact_maps[i].items():
                    val_j = fact_maps[j].get(subj)
                    if val_j and val_j != val_i:
                        try:
                            if float(val_i) != float(val_j):
                                conflicts.append((i, j, f"Conflict on '{subj}': {val_i} vs {val_j}"))
                        except ValueError:
                            pass
        return conflicts[:5]

    @staticmethod
    def _get_retry_recommendation(cr: float, fa: float, co: float):
        if cr < 0.30:
            return "retrieval", "Context not relevant — try broader search"
        if fa < 0.40:
            return "faithfulness", "Answer not grounded — increase top_k"
        if co < 0.35:
            return "completeness", "Answer incomplete — try web search"
        return None, None

    @staticmethod
    def _extract_keywords(text: str) -> set:
        words = re.findall(r"\b[a-zA-Z]{3,}\b", text.lower())
        return {w for w in words if w not in _STOP_WORDS}
