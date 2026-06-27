from __future__ import annotations
"""
Fusion Agent — Tier 4.
Merges all dept NL summaries into one coherent, cited answer.
Uses ConfidenceModel for confidence calculation and output decisions.
"""

import asyncio
import logging
from typing import List

import config
from models.nl_result import NLResult
from infrastructure.llm_client import get_llm
from agents.system.confidence_model import ConfidenceModel

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
        Delegates to ConfidenceModel for the calculation.
        """
        return ConfidenceModel.calculate_composite(dept_results)

    async def resolve_contradictions(self, dept_results: List[NLResult]) -> List[str]:
        """
        Detect contradictions between dept summaries using embedding cosine similarity
        + LLM verification. Only pairs with high topic similarity (cos > 0.70) are
        checked by the LLM — keeps the extra call count low.
        """
        if len(dept_results) < 2:
            return []

        import numpy as np
        from infrastructure.embedding_service import get_embedder

        embedder = get_embedder()
        try:
            embeddings = await asyncio.gather(*[
                embedder.embed(r.summary[:500]) for r in dept_results
            ])
        except Exception:
            return []

        contradictions: List[str] = []
        llm = get_llm()

        for i in range(len(dept_results)):
            for j in range(i + 1, len(dept_results)):
                v1 = np.array(embeddings[i])
                v2 = np.array(embeddings[j])
                norm = np.linalg.norm(v1) * np.linalg.norm(v2)
                cos_sim = float(np.dot(v1, v2) / (norm + 1e-9))

                # Only check pairs that share topic (high similarity) — different topics can't contradict
                if cos_sim < 0.70:
                    continue

                dept_a = dept_results[i].dept_tag or f"dept_{i}"
                dept_b = dept_results[j].dept_tag or f"dept_{j}"
                try:
                    verdict = await asyncio.wait_for(
                        llm.complete(
                            f"Statement 1 ({dept_a}): {dept_results[i].summary[:300]}\n"
                            f"Statement 2 ({dept_b}): {dept_results[j].summary[:300]}\n"
                            "Do these statements contradict each other on any factual point? "
                            "Reply YES or NO only.",
                            system="You detect factual contradictions between statements. Reply YES or NO only.",
                        ),
                        timeout=6.0,
                    )
                    if "YES" in verdict.upper():
                        contradictions.append(
                            f"Contradiction detected between {dept_a} and {dept_b} "
                            f"(topic similarity={cos_sim:.2f}) — verify with department heads"
                        )
                except Exception:
                    pass

        return contradictions

    def decide_output(self, merged_answer: str, confidence: float) -> dict:
        """
        Decision logic for output based on confidence.
        Uses ConfidenceModel.interpret_confidence to determine action.
        Returns {action: str, answer: str, confidence: float, warning: str}
        """
        interpretation = ConfidenceModel.interpret_confidence(confidence)

        action = "return"
        if interpretation["should_escalate"]:
            action = "fallback"
        elif interpretation["should_warn"]:
            action = "return_with_warning"

        warning = None
        if interpretation["should_warn"]:
            warning = (
                f"⚠️ Confidence moderate ({confidence:.0%}). "
                "Please verify this answer if it is critical to a decision."
            )
        elif interpretation["should_escalate"]:
            warning = (
                f"⚠️ Confidence low ({confidence:.0%}). "
                "Initiating escalation for a more reliable answer."
            )

        return {
            "action": action,
            "answer": merged_answer,
            "confidence": confidence,
            "warning": warning,
        }

    async def run(self, dept_results: List[NLResult]) -> dict:
        """Full fusion flow: merge → confidence → decide."""
        merged, contradictions = await asyncio.gather(
            self.merge_summaries(dept_results),
            self.resolve_contradictions(dept_results),
        )
        confidence = self.calculate_confidence(dept_results)
        decision = self.decide_output(merged, confidence)
        decision["contradictions"] = contradictions
        return decision
