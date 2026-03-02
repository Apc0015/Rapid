"""
Query Decomposer for Intelligent Auto-RAG.

Breaks complex, multi-part queries into focused sub-queries that can be
answered independently and then synthesized into a final answer.

Why decomposition matters:
  - "What is the revenue and who is the CEO?" → two separate retrieval tasks
  - A single embedding for a complex query is often weaker than embeddings
    for focused sub-queries
  - Allows routing different sub-questions to different pipelines
    (e.g., "total sales" → SQL, "why did sales decline?" → RAG)

Decomposition strategies:
  1. Heuristic (no LLM): pattern detection for conjunctions, comparisons,
     multi-part questions — fast, zero cost
  2. LLM-based: ask the LLM to decompose complex queries — higher quality
     but costs one extra API call

The system auto-selects: heuristic for simple queries (<15 words, single
question mark), LLM-based for complex multi-part queries.
"""

import re
import logging
from dataclasses import dataclass, field
from typing import List, Optional, Any

logger = logging.getLogger(__name__)

# Conjunction patterns that suggest multi-part questions
_CONJUNCTION_RE = re.compile(
    r"\b(and also|and then|as well as|furthermore|in addition|"
    r"additionally|what about|how about|along with)\b",
    re.IGNORECASE,
)

# Multi-question detector: "X? Y?"
_MULTI_QUESTION_RE = re.compile(r"\?[^?]*\?")

# Comparison patterns: "compare X with Y", "difference between X and Y"
_COMPARISON_RE = re.compile(
    r"\b(compare|comparison|difference between|versus|vs\.?|"
    r"contrast|which is better|pros and cons)\b",
    re.IGNORECASE,
)

# List-seeking patterns: "list all", "what are the", "enumerate"
_LIST_RE = re.compile(
    r"\b(list all|list the|what are all|enumerate|give me all|"
    r"tell me all)\b",
    re.IGNORECASE,
)


@dataclass
class DecomposedQuery:
    """Result of query decomposition."""
    original: str
    sub_queries: List[str]
    strategy: str              # "none" | "heuristic" | "llm"
    is_complex: bool           # True if decomposition was applied
    synthesis_hint: str        # How to combine sub-answers: "list" | "compare" | "merge"


class QueryDecomposer:
    """
    Decomposes complex multi-part queries into focused sub-queries.

    Usage:
        decomposer = QueryDecomposer()
        result = decomposer.decompose("What is the revenue and who is the CEO?")
        # result.sub_queries == ["What is the revenue?", "Who is the CEO?"]
    """

    def decompose(
        self,
        query: str,
        llm_client: Optional[Any] = None,
        force_llm: bool = False,
    ) -> DecomposedQuery:
        """
        Decompose a query into sub-queries.

        Args:
            query: The original user question.
            llm_client: Optional LangChain LLM for high-quality decomposition.
            force_llm: Force LLM decomposition even for simple queries.

        Returns:
            DecomposedQuery with sub-queries and synthesis hint.
        """
        query = query.strip()

        if not self._is_complex(query) and not force_llm:
            return DecomposedQuery(
                original=query,
                sub_queries=[query],
                strategy="none",
                is_complex=False,
                synthesis_hint="direct",
            )

        # LLM decomposition for complex queries
        if llm_client is not None:
            result = self._llm_decompose(query, llm_client)
            if result and len(result) > 1:
                synthesis_hint = self._detect_synthesis_hint(query)
                logger.info(
                    "QueryDecomposer (llm): '%s' → %d sub-queries",
                    query[:60], len(result),
                )
                return DecomposedQuery(
                    original=query,
                    sub_queries=result,
                    strategy="llm",
                    is_complex=True,
                    synthesis_hint=synthesis_hint,
                )

        # Heuristic decomposition fallback
        result = self._heuristic_decompose(query)
        synthesis_hint = self._detect_synthesis_hint(query)

        logger.info(
            "QueryDecomposer (heuristic): '%s' → %d sub-queries",
            query[:60], len(result),
        )

        return DecomposedQuery(
            original=query,
            sub_queries=result if len(result) > 1 else [query],
            strategy="heuristic" if len(result) > 1 else "none",
            is_complex=len(result) > 1,
            synthesis_hint=synthesis_hint,
        )

    def synthesize(
        self,
        original_query: str,
        sub_answers: List[str],
        synthesis_hint: str,
        llm_client: Optional[Any] = None,
    ) -> str:
        """
        Synthesize multiple sub-answers into a final coherent answer.

        Args:
            original_query: The original full question.
            sub_answers: List of answers to each sub-query.
            synthesis_hint: "list" | "compare" | "merge" | "direct"
            llm_client: LLM for synthesis (optional — falls back to concat).

        Returns:
            Synthesized answer string.
        """
        if not sub_answers:
            return "No answers available."

        if len(sub_answers) == 1:
            return sub_answers[0]

        if llm_client is not None:
            return self._llm_synthesize(original_query, sub_answers, llm_client)

        # Simple fallback: concatenate with numbering
        if synthesis_hint == "compare":
            return "\n\n".join(f"**Point {i+1}:** {a}" for i, a in enumerate(sub_answers))
        elif synthesis_hint == "list":
            return "\n\n".join(sub_answers)
        else:
            return "\n\n".join(sub_answers)

    # ── Complexity detection ───────────────────────────────────────────────────

    @staticmethod
    def _is_complex(query: str) -> bool:
        """Determine if a query is complex enough to warrant decomposition."""
        # Short queries are usually simple
        if len(query.split()) < 10:
            return False

        # Multiple question marks
        if _MULTI_QUESTION_RE.search(query):
            return True

        # Explicit conjunctions suggesting multiple requests
        if _CONJUNCTION_RE.search(query):
            return True

        # Comparison patterns
        if _COMPARISON_RE.search(query):
            return True

        # Many question words in one sentence
        q_words = re.findall(r"\b(what|who|when|where|why|how|which)\b", query.lower())
        if len(q_words) >= 3:
            return True

        return False

    @staticmethod
    def _detect_synthesis_hint(query: str) -> str:
        """Detect how sub-answers should be combined."""
        q_lower = query.lower()
        if _COMPARISON_RE.search(q_lower):
            return "compare"
        if _LIST_RE.search(q_lower):
            return "list"
        return "merge"

    # ── Heuristic decomposition ────────────────────────────────────────────────

    @staticmethod
    def _heuristic_decompose(query: str) -> List[str]:
        """Split a query into sub-queries using pattern matching."""
        # Try splitting on "and also", "as well as", etc.
        parts = _CONJUNCTION_RE.split(query)
        if len(parts) >= 3:
            # Extract the text parts (split() also returns the matched groups)
            clean_parts = [p.strip() for p in parts if p.strip() and not _CONJUNCTION_RE.fullmatch(p.strip())]
            if len(clean_parts) >= 2:
                # Ensure each part is a proper question
                return [_ensure_question(p) for p in clean_parts if len(p.split()) >= 3]

        # Try splitting on multiple "?" question marks
        if _MULTI_QUESTION_RE.search(query):
            questions = re.split(r"\?", query)
            clean = [q.strip() + "?" for q in questions if q.strip() and len(q.strip().split()) >= 3]
            if len(clean) >= 2:
                return clean

        # Try splitting on "and" when followed by another verb phrase
        and_split = re.split(r"\band\b", query, flags=re.IGNORECASE)
        if len(and_split) == 2:
            a, b = and_split[0].strip(), and_split[1].strip()
            if len(a.split()) >= 4 and len(b.split()) >= 3:
                # Only split if both parts look like meaningful phrases
                return [_ensure_question(a), _ensure_question(b)]

        return [query]

    # ── LLM decomposition ─────────────────────────────────────────────────────

    @staticmethod
    def _llm_decompose(query: str, llm_client: Any) -> List[str]:
        """Use LLM to decompose a complex query into sub-questions."""
        from langchain_core.messages import HumanMessage
        prompt = (
            "You are a question decomposition assistant.\n"
            "Break the following complex question into 2-4 focused, independent sub-questions.\n"
            "Each sub-question should be answerable on its own.\n"
            "If the question is already simple, return it as-is in a list.\n\n"
            f"Question: {query}\n\n"
            "Return ONLY a JSON array of sub-question strings, e.g.:\n"
            '[\"Sub-question 1\", \"Sub-question 2\"]\n\n'
            "JSON array:"
        )
        try:
            response = llm_client.invoke([HumanMessage(content=prompt)])
            text = response.content.strip()
            # Extract JSON array
            match = re.search(r"\[.*\]", text, re.DOTALL)
            if match:
                import json as _json
                questions = _json.loads(match.group())
                if isinstance(questions, list) and all(isinstance(q, str) for q in questions):
                    return [q.strip() for q in questions if q.strip()]
        except Exception as e:
            logger.debug("LLM decompose failed: %s", e)
        return [query]

    # ── LLM synthesis ─────────────────────────────────────────────────────────

    @staticmethod
    def _llm_synthesize(
        original_query: str,
        sub_answers: List[str],
        llm_client: Any,
    ) -> str:
        """Use LLM to synthesize multiple sub-answers into a coherent final answer."""
        from langchain_core.messages import HumanMessage

        numbered = "\n".join(
            f"Answer {i+1}: {a}" for i, a in enumerate(sub_answers)
        )
        prompt = (
            f"Original question: {original_query}\n\n"
            f"Partial answers:\n{numbered}\n\n"
            "Synthesize the partial answers into a single, coherent, complete response "
            "to the original question. Do not add information not present in the partial answers.\n\n"
            "Final answer:"
        )
        try:
            response = llm_client.invoke([HumanMessage(content=prompt)])
            return response.content.strip()
        except Exception as e:
            logger.warning("LLM synthesis failed: %s", e)
            return "\n\n".join(sub_answers)


def _ensure_question(text: str) -> str:
    """Make sure text ends with a question mark."""
    text = text.strip().rstrip(".,;")
    if not text.endswith("?"):
        text += "?"
    # Capitalize first letter
    if text and text[0].islower():
        text = text[0].upper() + text[1:]
    return text
