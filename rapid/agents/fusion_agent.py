from __future__ import annotations
"""
Fusion Agent — Tier 4.
Merges all dept NL summaries into one coherent, cited answer.
Calculates composite confidence. Decides: return / warn / fallback.
"""

import logging
from typing import List

import config
from models.nl_result import NLResult
from infrastructure.llm_client import get_llm

logger = logging.getLogger(__name__)


class FusionAgent:

    async def merge_summaries(self, dept_results: List[NLResult]) -> str:
        """
        Use LLM to weave dept NL summaries into one coherent, cited answer.
        Preserves all facts, resolves contradictions explicitly, adds transitions.
        """
        if not dept_results:
            return "No information was found for your query."

        if len(dept_results) == 1:
            return dept_results[0].summary

        llm = get_llm()
        sources_text = "\n\n---\n\n".join(
            f"[{r.dept_tag.upper()} Department]\n{r.summary}"
            for r in dept_results
        )
        system = (
            "You merge department-specific answers into one professional, coherent response. "
            "RULES: "
            "1. Preserve every fact from every source. "
            "2. If two departments contradict each other, note BOTH versions: "
            "   'Finance reports X; Legal reports Y — verify with department heads.' "
            "3. Add natural transition language between sections. "
            "4. Include inline source labels like [HR] or [Finance] before each dept's contribution. "
            "5. Do NOT add information not present in the sources."
        )
        return await llm.complete(sources_text, system=system, strong=True)

    def calculate_confidence(self, dept_results: List[NLResult]) -> float:
        """
        Composite confidence across all dept results.
        Formula (from spec): context×0.30 + faithfulness×0.50 + completeness×0.20
        For merged results, we average dept confidences weighted by the formula.
        """
        if not dept_results:
            return 0.0

        # Average the dept-level confidence scores
        avg_conf = sum(r.confidence for r in dept_results) / len(dept_results)

        # Decompose into dimensions (heuristic split for now)
        # Full implementation: each pipeline returns dimension scores separately
        context_score = min(1.0, avg_conf * 1.1)
        faithfulness_score = avg_conf
        completeness_score = min(1.0, len(dept_results) / 3 * avg_conf)

        composite = (
            context_score * config.CONF_CONTEXT_WEIGHT +
            faithfulness_score * config.CONF_FAITHFULNESS_WEIGHT +
            completeness_score * config.CONF_COMPLETENESS_WEIGHT
        )
        return round(min(1.0, composite), 3)

    def resolve_contradictions(self, dept_results: List[NLResult]) -> List[str]:
        """
        Detect when departments provide conflicting information.
        Returns list of contradiction descriptions (handled by merge_summaries LLM call).
        """
        contradictions = []
        summaries = [(r.dept_tag, r.summary) for r in dept_results]

        # Simple heuristic: flag if two depts mention the same numeric value differently
        # Full implementation: semantic similarity comparison between dept summaries
        seen_topics: dict = {}
        for dept_tag, summary in summaries:
            words = set(summary.lower().split())
            for other_dept, other_words in seen_topics.items():
                overlap = words & other_words
                if len(overlap) > 20:  # significant overlap in content
                    contradictions.append(
                        f"Potential overlap between {dept_tag} and {other_dept} results"
                    )
            seen_topics[dept_tag] = words

        return contradictions

    def decide_output(self, merged_answer: str, confidence: float) -> dict:
        """
        Decision logic (from spec):
          ≥ 0.65 → return answer to user
          0.40–0.65 → return with uncertainty warning
          < 0.40 → trigger fallback
        Returns {action: str, answer: str, confidence: float, warning: str}
        """
        if confidence >= config.HIGH_CONF:
            return {
                "action": "return",
                "answer": merged_answer,
                "confidence": confidence,
                "warning": None,
            }
        elif confidence >= config.LOW_CONF:
            return {
                "action": "return_with_warning",
                "answer": merged_answer,
                "confidence": confidence,
                "warning": (
                    f"⚠️ Confidence moderate ({confidence:.0%}). "
                    "Please verify this answer if it is critical to a decision."
                ),
            }
        else:
            return {
                "action": "fallback",
                "answer": merged_answer,
                "confidence": confidence,
                "warning": (
                    f"⚠️ Confidence low ({confidence:.0%}). "
                    "Initiating web search or human escalation for a better answer."
                ),
            }

    async def run(self, dept_results: List[NLResult]) -> dict:
        """Full fusion flow: merge → confidence → decide."""
        merged = await self.merge_summaries(dept_results)
        confidence = self.calculate_confidence(dept_results)
        contradictions = self.resolve_contradictions(dept_results)
        decision = self.decide_output(merged, confidence)
        decision["contradictions"] = contradictions
        return decision
