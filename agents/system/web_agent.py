from __future__ import annotations
"""
Web Agent — Tier 3 Infrastructure.
External fallback only. Activated when Fusion confidence < LOW_CONF (0.40)
and no internal source can improve it. Never used as primary source.

Search powered by Serper.dev (Google Search API).
"""

import logging
import os
from typing import List

import aiohttp

from models.nl_result import NLResult
from infrastructure.llm_client import get_llm

logger = logging.getLogger(__name__)

SERPER_API_KEY = os.getenv("SERPER_API_KEY", "")
SERPER_ENDPOINT = "https://google.serper.dev/search"


class WebAgent:
    """
    Searches public web for supplementary information.
    Only activated by FusionAgent when internal confidence < 0.40.
    """

    async def search_web(self, query: str, context: str) -> List[dict]:
        """
        Formulate optimised search query and call Serper.dev (Google Search).
        Returns top 5 results with url, title, snippet.
        """
        if not SERPER_API_KEY:
            logger.warning("SERPER_API_KEY not set — web search disabled")
            return [{"url": "web_search_not_configured", "title": query, "snippet": ""}]

        llm = get_llm()
        # Rewrite the query for web search
        system = (
            "You rewrite an internal business question into an effective web search query. "
            "Add relevant industry context. Return only the search query string, nothing else."
        )
        search_query = await llm.complete(
            f"Original question: {query}\nInternal context: {context[:200]}",
            system=system,
        )
        search_query = search_query.strip().strip('"')
        logger.info(f"[WebAgent] Searching Serper: '{search_query}'")

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    SERPER_ENDPOINT,
                    headers={
                        "X-API-KEY":    SERPER_API_KEY,
                        "Content-Type": "application/json",
                    },
                    json={"q": search_query, "num": 5},
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status != 200:
                        body = await resp.text()
                        logger.warning(f"[WebAgent] Serper returned {resp.status}: {body[:200]}")
                        return []
                    data = await resp.json()

            results = []
            # Organic results
            for item in data.get("organic", [])[:5]:
                results.append({
                    "url":     item.get("link", ""),
                    "title":   item.get("title", ""),
                    "snippet": item.get("snippet", ""),
                })
            # Answer box (if present) — prepend as a high-quality result
            if "answerBox" in data:
                ab = data["answerBox"]
                results.insert(0, {
                    "url":     ab.get("link", ""),
                    "title":   ab.get("title", "Answer"),
                    "snippet": ab.get("answer") or ab.get("snippet", ""),
                })
            logger.info(f"[WebAgent] Serper returned {len(results)} results")
            return results

        except Exception as e:
            logger.warning(f"[WebAgent] Serper search failed: {e}")
            return []

    async def fetch_and_summarise(self, urls: List[str], query: str) -> tuple[str, List[str]]:
        """
        Fetch page content, strip HTML, summarise with LLM.
        Returns (nl_summary, source_citations).
        """
        llm = get_llm()
        texts = []
        valid_urls = []

        for url in urls:
            if url == "web_search_not_configured":
                continue
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                        html = await resp.text()
                        # Strip HTML tags (basic)
                        import re
                        text = re.sub(r"<[^>]+>", " ", html)
                        text = re.sub(r"\s+", " ", text).strip()[:3000]
                        texts.append(text)
                        valid_urls.append(url)
            except Exception as e:
                logger.warning(f"Failed to fetch {url}: {e}")

        if not texts:
            return "No external sources could be retrieved.", []

        context = "\n\n---\n\n".join(texts)
        system = (
            "You summarise web content to answer a business question. "
            "Only include information relevant to the question. "
            "Be factual. Note the source credibility limitations of web content."
        )
        summary = await llm.complete(f"Question: {query}\n\nWeb content:\n{context}", system=system)
        return summary, valid_urls

    def assess_credibility(self, sources: List[str]) -> List[dict]:
        """Score sources on credibility signals."""
        trusted_domains = {
            ".gov", ".edu", "reuters.com", "bbc.com", "ft.com",
            "wsj.com", "economist.com", "hbr.org",
        }
        results = []
        for url in sources:
            score = 0.5  # default
            for domain in trusted_domains:
                if domain in url:
                    score = 0.85
                    break
            results.append({"url": url, "credibility": score})
        return results

    async def run(self, query: str, internal_context: str) -> NLResult:
        """Full web agent flow: search → summarise snippets → optionally fetch pages."""
        raw_results = await self.search_web(query, internal_context)

        # Filter out placeholder / empty results
        valid = [r for r in raw_results if r.get("url") and r["url"] != "web_search_not_configured"]

        if not valid:
            return NLResult(
                summary=(
                    "Web search is not configured or returned no results. "
                    "Internal sources were used for this answer."
                ),
                source="web",
                confidence=0.1,
            )

        # ── Fast path: summarise snippets directly (no page fetch needed) ──────
        snippet_context = "\n\n".join(
            f"Source: {r['url']}\nTitle: {r['title']}\n{r['snippet']}"
            for r in valid if r.get("snippet")
        )
        citations = [r["url"] for r in valid if r.get("url")]

        if snippet_context:
            llm = get_llm()
            system = (
                "You answer a question using web search snippets. "
                "Be factual, concise, and cite which source supports each point. "
                "Note that web sources may not reflect internal company data."
            )
            summary = await llm.complete(
                f"Question: {query}\n\nSearch results:\n{snippet_context}",
                system=system,
            )
            credibility = self.assess_credibility(citations)
            avg_cred = sum(c["credibility"] for c in credibility) / len(credibility) if credibility else 0.5
            confidence = round(min(0.75, 0.45 + avg_cred * 0.3), 2)
            return NLResult(
                summary=f"[Web sources]\n{summary}",
                source="web",
                confidence=confidence,
                citations=citations,
            )

        # ── Slow path: fetch full pages when snippets are empty ───────────────
        credible_urls = [s["url"] for s in self.assess_credibility(citations) if s["credibility"] >= 0.5]
        summary, fetched_citations = await self.fetch_and_summarise(credible_urls or citations, query)
        return NLResult(
            summary=f"[Web sources]\n{summary}",
            source="web",
            confidence=0.50,
            citations=fetched_citations,
        )
