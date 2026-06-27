"""
confidence_model.py — Centralized confidence scoring and interpretation.
Extracted from FusionAgent and BaseDeptAgent for clarity and reusability.
"""

import logging
from typing import List
from models.nl_result import NLResult
import config

logger = logging.getLogger(__name__)


class ConfidenceModel:
    """Encapsulates confidence calculation, interpretation, and escalation logic."""

    # Confidence thresholds (from spec)
    HIGH_CONFIDENCE = 0.65
    UNCERTAIN_LOWER = 0.40
    UNCERTAIN_UPPER = 0.65
    LOW_CONFIDENCE = 0.40

    @staticmethod
    def calculate_composite(dept_results: List[NLResult]) -> float:
        """
        Calculate composite confidence for merged multi-dept results.

        Formula: context×0.30 + faithfulness×0.50 + completeness×0.20
        Approximates dimensions from dept-level confidence averages.
        """
        if not dept_results:
            return 0.0

        avg_dept_conf = sum(r.confidence for r in dept_results) / len(dept_results)

        context_score = min(1.0, avg_dept_conf * 1.1)
        faithfulness_score = avg_dept_conf
        completeness_score = min(1.0, len(dept_results) / 3 * avg_dept_conf)

        composite = (
            context_score * config.CONF_CONTEXT_WEIGHT +
            faithfulness_score * config.CONF_FAITHFULNESS_WEIGHT +
            completeness_score * config.CONF_COMPLETENESS_WEIGHT
        )
        return round(min(1.0, composite), 3)

    @staticmethod
    def interpret_confidence(confidence: float) -> dict:
        """
        Interpret a confidence score and suggest action.

        Returns:
            {
                "level": "high" | "uncertain" | "low",
                "should_return": bool,
                "should_warn": bool,
                "should_escalate": bool,
            }
        """
        if confidence >= ConfidenceModel.HIGH_CONFIDENCE:
            return {
                "level": "high",
                "should_return": True,
                "should_warn": False,
                "should_escalate": False,
            }
        elif ConfidenceModel.UNCERTAIN_LOWER <= confidence < ConfidenceModel.HIGH_CONFIDENCE:
            return {
                "level": "uncertain",
                "should_return": True,
                "should_warn": True,
                "should_escalate": False,
            }
        else:  # < 0.40
            return {
                "level": "low",
                "should_return": False,
                "should_warn": False,
                "should_escalate": True,
            }

    @staticmethod
    def merge_dept_confidences(rag_conf: float, db_conf: float) -> float:
        """
        Merge RAG and DB pipeline confidence scores for a single department.

        Formula: RAG×0.4 + DB×0.6 (DB typically more reliable)
        """
        return round(rag_conf * 0.4 + db_conf * 0.6, 3)
