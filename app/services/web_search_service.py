from typing import List, Dict, Optional
import os
import httpx


class WebSearchService:
    """Web search service supporting multiple providers."""

    def __init__(self):
        self.google_api_key = os.getenv("GOOGLE_SEARCH_API_KEY")
        self.google_cx = os.getenv("GOOGLE_SEARCH_CX")
        self.tavily_api_key = os.getenv("TAVILY_API_KEY")
        self.bing_api_key = os.getenv("BING_SEARCH_API_KEY")
        self.default_provider = os.getenv("DEFAULT_SEARCH_PROVIDER", "tavily")

    async def search(
        self,
        query: str,
        num_results: int = 5,
        provider: Optional[str] = None,
    ) -> List[Dict]:
        provider = provider or self.default_provider
        if provider == "google":
            return await self._google_search(query, num_results)
        if provider == "tavily":
            return await self._tavily_search(query, num_results)
        if provider == "bing":
            return await self._bing_search(query, num_results)
        raise ValueError(f"Unknown search provider: {provider}")

    async def _tavily_search(self, query: str, num_results: int) -> List[Dict]:
        if not self.tavily_api_key:
            raise ValueError("Tavily API key not configured")
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": self.tavily_api_key,
                    "query": query,
                    "max_results": num_results,
                    "search_depth": "advanced",
                    "include_answer": True,
                    "include_raw_content": False,
                },
                timeout=10.0,
            )
            response.raise_for_status()
            data = response.json()
        results: List[Dict] = []
        for result in data.get("results", []):
            results.append({
                "title": result.get("title", ""),
                "snippet": result.get("content", ""),
                "url": result.get("url", ""),
                "date": result.get("published_date"),
                "score": result.get("score", 0.0),
                "source": "tavily",
            })
        if data.get("answer"):
            results.insert(0, {
                "title": "AI-Generated Summary",
                "snippet": data["answer"],
                "url": "",
                "date": None,
                "score": 1.0,
                "source": "tavily_answer",
            })
        return results

    async def _google_search(self, query: str, num_results: int) -> List[Dict]:
        if not self.google_api_key or not self.google_cx:
            raise ValueError("Google Search API not configured")
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://www.googleapis.com/customsearch/v1",
                params={
                    "key": self.google_api_key,
                    "cx": self.google_cx,
                    "q": query,
                    "num": num_results,
                },
                timeout=10.0,
            )
            response.raise_for_status()
            data = response.json()
        results: List[Dict] = []
        for item in data.get("items", []):
            results.append({
                "title": item.get("title", ""),
                "snippet": item.get("snippet", ""),
                "url": item.get("link", ""),
                "date": item.get("pagemap", {}).get("metatags", [{}])[0].get("article:published_time"),
                "score": 1.0,
                "source": "google",
            })
        return results

    async def _bing_search(self, query: str, num_results: int) -> List[Dict]:
        if not self.bing_api_key:
            raise ValueError("Bing Search API not configured")
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://api.bing.microsoft.com/v7.0/search",
                headers={"Ocp-Apim-Subscription-Key": self.bing_api_key},
                params={"q": query, "count": num_results, "responseFilter": "Webpages"},
                timeout=10.0,
            )
            response.raise_for_status()
            data = response.json()
        results: List[Dict] = []
        for item in data.get("webPages", {}).get("value", []):
            results.append({
                "title": item.get("name", ""),
                "snippet": item.get("snippet", ""),
                "url": item.get("url", ""),
                "date": item.get("dateLastCrawled"),
                "score": 1.0,
                "source": "bing",
            })
        return results
