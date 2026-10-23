"""Web search capability using multiple search backends."""

from __future__ import annotations

import json
import re
import time
from typing import Any

import httpx

from wish_granter.capabilities.base import Capability, CapabilityResult


class WebSearchCapability(Capability):
    name = "web_search"
    description = "Search the web for information using DDG/SearXNG"

    SEARCH_ENGINES = {
        "ddg": "https://api.duckduckgo.com/",
        "searxng": "http://localhost:8888/search",
    }

    async def execute(self, params: dict[str, Any]) -> CapabilityResult:
        start = time.time()
        query = params.get("query", "")
        max_results = params.get("max_results", 10)
        engine = params.get("engine", "ddg")

        if not query:
            return self._result(False, error="No search query provided", start_time=start)

        try:
            results = await self._search_ddg(query, max_results)
            return self._result(
                True,
                data={"query": query, "results": results, "total": len(results)},
                start_time=start,
            )
        except Exception as e:
            return self._result(False, error=str(e), start_time=start)

    async def _search_ddg(self, query: str, max_results: int = 10) -> list[dict[str, Any]]:
        results = []
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                "https://html.duckduckgo.com/html/",
                params={"q": query, "kl": "us-en"},
                headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"},
            )
            text = resp.text
            link_pattern = re.compile(r'<a rel="nofollow" class="result__a" href="([^"]+)"[^>]*>(.*?)</a>', re.DOTALL)
            snippet_pattern = re.compile(r'<a class="result__snippet"[^>]*>(.*?)</a>', re.DOTALL)

            links = link_pattern.findall(text)
            snippets = snippet_pattern.findall(text)

            for i, (url, title) in enumerate(links[:max_results]):
                clean_title = re.sub(r'<[^>]+>', '', title).strip()
                snippet = re.sub(r'<[^>]+>', '', snippets[i]).strip() if i < len(snippets) else ""
                results.append({
                    "title": clean_title,
                    "url": url,
                    "snippet": snippet,
                    "rank": i + 1,
                })

        return results