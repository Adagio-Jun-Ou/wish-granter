"""Web scraping capability - extract content from web pages."""

from __future__ import annotations

import re
import time
from typing import Any

import httpx
from bs4 import BeautifulSoup

from wish_granter.capabilities.base import Capability, CapabilityResult


class WebScraperCapability(Capability):
    name = "web_scraper"
    description = "Scrape and extract content from web pages"

    async def execute(self, params: dict[str, Any]) -> CapabilityResult:
        start = time.time()
        url = params.get("url", "")
        extract = params.get("extract", "text")
        selector = params.get("selector", "")
        headers = params.get("headers", {})

        if not url:
            return self._result(False, error="No URL provided", start_time=start)

        if not url.startswith(("http://", "https://")):
            url = f"https://{url}"

        try:
            default_headers = {
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            }
            default_headers.update(headers)

            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                resp = await client.get(url, headers=default_headers)
                resp.raise_for_status()

            soup = BeautifulSoup(resp.text, "html.parser")

            for tag in soup(["script", "style", "nav", "footer", "header"]):
                tag.decompose()

            if extract == "text":
                result = self._extract_text(soup)
            elif extract == "links":
                result = self._extract_links(soup, url)
            elif extract == "images":
                result = self._extract_images(soup, url)
            elif extract == "structured":
                result = self._extract_structured(soup)
            elif extract == "selector" and selector:
                elements = soup.select(selector)
                result = [{"tag": el.name, "text": el.get_text(strip=True), "attrs": dict(el.attrs)} for el in elements[:50]]
            else:
                result = self._extract_text(soup)

            return self._result(True, data=result, start_time=start)
        except Exception as e:
            return self._result(False, error=str(e), start_time=start)

    def _extract_text(self, soup: BeautifulSoup) -> dict[str, Any]:
        title = soup.find("title")
        title_text = title.get_text(strip=True) if title else ""
        meta_desc = soup.find("meta", attrs={"name": "description"})
        description = meta_desc.get("content", "") if meta_desc else ""
        text = soup.get_text(separator="\n", strip=True)
        paragraphs = [p.get_text(strip=True) for p in soup.find_all("p") if p.get_text(strip=True)]
        headings = [h.get_text(strip=True) for h in soup.find_all(["h1", "h2", "h3"]) if h.get_text(strip=True)]

        return {
            "title": title_text,
            "description": description,
            "text": text[:10000],
            "paragraphs": paragraphs[:50],
            "headings": headings[:20],
            "word_count": len(text.split()),
        }

    def _extract_links(self, soup: BeautifulSoup, base_url: str) -> dict[str, Any]:
        links = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if href.startswith("/"):
                from urllib.parse import urljoin
                href = urljoin(base_url, href)
            links.append({
                "text": a.get_text(strip=True)[:100],
                "url": href,
            })
        return {"links": links[:200], "total": len(links)}

    def _extract_images(self, soup: BeautifulSoup, base_url: str) -> dict[str, Any]:
        images = []
        for img in soup.find_all("img"):
            src = img.get("src", "")
            if src.startswith("/"):
                from urllib.parse import urljoin
                src = urljoin(base_url, src)
            images.append({
                "src": src,
                "alt": img.get("alt", ""),
                "width": img.get("width"),
                "height": img.get("height"),
            })
        return {"images": images[:50], "total": len(images)}

    def _extract_structured(self, soup: BeautifulSoup) -> dict[str, Any]:
        tables = []
        for table in soup.find_all("table"):
            rows = []
            for tr in table.find_all("tr"):
                cells = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
                if cells:
                    rows.append(cells)
            if rows:
                tables.append({"rows": rows[:100], "columns": len(rows[0]) if rows else 0})

        lists = []
        for ul in soup.find_all(["ul", "ol"]):
            items = [li.get_text(strip=True) for li in ul.find_all("li")]
            if items:
                lists.append(items[:50])

        return {"tables": tables[:10], "lists": lists[:20]}