"""
Web Search Agent

Fires when internal confidence < 0.65.
Fetches web results and converts them to NL summary (same isolation rule as R4).
Raw web snippets never leave this module.
"""

import logging
from dataclasses import dataclass, field
from typing import List, Optional

from app.services.web_search_service import WebSearchService
from app.services.llm_service import LLMManager
from app.core.confidence import HIGH_CONFIDENCE

logger = logging.getLogger(__name__)


@dataclass
class WebSourceCitation:
    url: str
    title: str
    date_retrieved: Optional[str]
    search_provider: str


@dataclass
class WebSearchResult:
    nl_summary: str                         # NL paragraph only
    sources: List[WebSourceCitation]        # URLs and titles (no raw snippets)
    confidence: float


class WebSearchAgent:
    """
    Web search agent with NL isolation.
    Only fires when internal confidence < HIGH_CONFIDENCE threshold.
    """

    def __init__(
        self,
        web_service: WebSearchService,
        llm_manager: LLMManager,
    ):
        self.web = web_service
        self.llm = llm_manager

    async def search_and_summarize(
        self,
        raw_query: str,
        internal_confidence: float,
    ) -> Optional[WebSearchResult]:
        """
        Search web and convert results to NL summary.

        Only fires if internal_confidence < HIGH_CONFIDENCE (0.65).
        Raw snippets are consumed here and never returned.
        """
        if internal_confidence >= HIGH_CONFIDENCE:
            logger.debug("Web agent: skipping (confidence %.2f >= %.2f)", internal_confidence, HIGH_CONFIDENCE)
            return None

        try:
            raw_results = await self.web.search(raw_query, num_results=5)
        except Exception as e:
            logger.warning("Web search failed: %s", e)
            return None

        if not raw_results:
            return None

        # Build source citations before consuming snippets
        sources = []
        for r in raw_results:
            if r.get("url"):
                sources.append(WebSourceCitation(
                    url=r.get("url", ""),
                    title=r.get("title", ""),
                    date_retrieved=r.get("date"),
                    search_provider=r.get("source", "web"),
                ))

        # Build context for LLM (internal only — never returned)
        snippets = []
        for r in raw_results[:5]:
            if r.get("snippet") and r.get("title"):
                snippets.append(f"[{r['title']}]\n{r['snippet']}")

        if not snippets:
            return None

        context = "\n\n".join(snippets)

        prompt = f"""Answer the following question using information from web search results.

Question: {raw_query}

Web search results:
{context}

Write a concise NL paragraph (2-4 sentences) summarizing what the web results say about this question.
Only include information directly from the results above.
Do not mention "according to search results" or similar phrases."""

        try:
            nl_summary = await self.llm.chat(prompt, max_tokens=400, temperature=0.0)
        except Exception as e:
            logger.error("Web NL summary failed: %s", e)
            return None

        # Raw snippets are discarded — return only NL summary + source metadata
        confidence = min(0.60, internal_confidence + 0.15)  # web boosts confidence slightly
        return WebSearchResult(
            nl_summary=nl_summary,
            sources=sources,
            confidence=confidence,
        )
