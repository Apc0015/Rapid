"""
LLM Brain — Brain 1

The only component that calls the LLM for intent extraction and final answer.
Deliberately ignorant of data sources, schema, raw data, or governance rules.

Privacy guarantees:
- extract_intent() LLM call sees ONLY: user question
- compose_final_answer() LLM call sees ONLY: question + fused NL summary
- Intent and BrainResponse dataclasses have no raw data fields
"""

import json
import logging
from dataclasses import dataclass, field
from typing import List, Optional

from app.core.confidence import ConfidenceResult
from app.services.llm_service import LLMManager

logger = logging.getLogger(__name__)

VALID_TRACKS = {"rag", "db", "both", "neither"}


@dataclass
class Intent:
    raw_query: str
    tracks_needed: List[str]        # ["rag"] | ["db"] | ["both"] | ["neither"]
    department_hint: Optional[str]  # dept inferred from question phrasing
    confidence: float               # LLM's routing confidence
    # No raw data fields — structural privacy guarantee


@dataclass
class BrainResponse:
    answer: str
    confidence_result: Optional[ConfidenceResult]
    sources: List               # Source citations from agents (not LLM-generated)
    tracks_used: List[str]
    # No raw data fields — structural privacy guarantee


class LLMBrain:
    """
    Brain 1 — intent extraction and answer composition.

    The LLM is kept ignorant of:
    - Database existence, schema, table names, column names
    - Raw query results or document chunks
    - Governance rules or privacy policies
    """

    def __init__(self, llm_manager: LLMManager):
        self.llm = llm_manager

    async def extract_intent(
        self, user_question: str, user_department: str = "general"
    ) -> Intent:
        """
        Convert user question to structured Intent.

        LLM call receives ONLY: the user's question.
        Returns which tracks to activate and any department hint.
        """
        prompt = f"""Classify what data source(s) are needed to answer this question.

Question: "{user_question}"

Options:
- "rag": answer comes from uploaded documents (policies, reports, manuals, etc.)
- "db": answer requires live database data (numbers, records, transactions, metrics)
- "both": requires both documents and database data
- "neither": general conversation or knowledge question (no internal data needed)

Also identify if the question implies a specific department (e.g., Finance, HR, Sales, IT, Legal, Operations, Engineering).

Return ONLY valid JSON:
{{
  "tracks": "rag|db|both|neither",
  "department_hint": "DepartmentName or null",
  "routing_confidence": 0.0-1.0
}}"""

        tracks = ["rag"]  # default
        dept_hint = None
        routing_confidence = 0.7

        try:
            raw = await self.llm.chat(prompt, max_tokens=100, temperature=0.0)
            start = raw.find("{")
            end = raw.rfind("}") + 1
            if start >= 0 and end > start:
                data = json.loads(raw[start:end])
                track_str = data.get("tracks", "rag")
                if track_str in VALID_TRACKS:
                    tracks = [track_str]
                dept = data.get("department_hint")
                if dept and dept != "null" and dept.lower() != "null":
                    dept_hint = dept
                routing_confidence = float(data.get("routing_confidence", 0.7))
        except Exception as e:
            logger.warning("Intent extraction failed, defaulting to RAG: %s", e)

        intent = Intent(
            raw_query=user_question,
            tracks_needed=tracks,
            department_hint=dept_hint or user_department,
            confidence=routing_confidence,
        )
        logger.info(
            "Intent: tracks=%s dept=%s confidence=%.2f",
            tracks, dept_hint, routing_confidence,
        )
        return intent

    async def compose_final_answer(
        self,
        user_question: str,
        fused_nl_summary: str,
        sources: List,
        confidence_result: Optional[ConfidenceResult],
        tracks_used: List[str],
    ) -> BrainResponse:
        """
        Compose final answer for the user.

        LLM call receives ONLY: user question + fused NL summary.
        Source citations are attached from agent metadata — not LLM-generated.
        """
        if not fused_nl_summary:
            return BrainResponse(
                answer=(
                    "I searched your documents, your database, and the web. "
                    "I cannot find a reliable answer to this question."
                ),
                confidence_result=confidence_result,
                sources=[],
                tracks_used=tracks_used,
            )

        # Check if it's a "no data" result
        no_data_phrases = [
            "does not appear to contain", "no database connection",
            "no relevant information", "query returned no results",
        ]
        if any(p in fused_nl_summary.lower() for p in no_data_phrases):
            return BrainResponse(
                answer=fused_nl_summary,
                confidence_result=confidence_result,
                sources=sources,
                tracks_used=tracks_used,
            )

        prompt = f"""Answer the user's question using the information provided below.

User question: {user_question}

Information from internal sources:
{fused_nl_summary}

Instructions:
- Write a clear, direct answer in 2-5 sentences
- Preserve all specific figures, percentages, and facts exactly as given
- If the information is from multiple sources, integrate them coherently
- Do not add information not present in the context above
- Do not mention "based on the information" or similar preambles — just answer directly"""

        try:
            answer = await self.llm.chat(prompt, max_tokens=600, temperature=0.0)
        except Exception as e:
            logger.error("LLM answer composition failed: %s", e)
            answer = fused_nl_summary  # fallback to raw summary

        return BrainResponse(
            answer=answer,
            confidence_result=confidence_result,
            sources=sources,
            tracks_used=tracks_used,
        )
