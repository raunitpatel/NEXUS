"""
Wikipedia tool for the NEXUS Tool Agent.

Calls the Wikipedia REST API (no key required).
Searches for the query, fetches the page summary/extract.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

import httpx
import structlog
from config import settings

logger = structlog.get_logger(__name__)

_SEARCH_URL = f"{settings.wikipedia_api_base_url}/page/summary"


class WikipediaTool:
    """
    Fetches a Wikipedia article summary for a given search query.

    Uses the Wikipedia REST API /page/summary/{title} endpoint.
    Performs a search first to resolve the canonical page title.
    """

    async def run(self, query: str) -> dict[str, Any]:
        """
        Return a Wikipedia summary for the given query.

        Args:
            query: Search query string (e.g. "Hamlet Shakespeare").

        Returns:
            Dict with title, summary (first paragraph), url, and thumbnail_url.
            On error, returns dict with 'error' key.
        """
        logger.debug("wikipedia.run", query=query)

        # Normalize: Wikipedia REST API works best with the page title
        # Use the search API to find canonical title first
        try:
            title, summary, url = await self._fetch_summary(query)
        except Exception as exc:
            logger.warning("wikipedia.fetch_failed", query=query, error=str(exc))
            return {"error": f"Wikipedia lookup failed for '{query}': {exc}"}

        return {
            "title": title,
            "summary": summary,
            "url": url,
            "query": query,
        }

    async def _fetch_summary(self, query: str) -> tuple[str, str, str]:
        """
        Fetch Wikipedia page summary for the given query.

        Tries exact title first, then falls back to search API.

        Args:
            query: Query string.

        Returns:
            Tuple of (page_title, extract_text, page_url).

        Raises:
            httpx.HTTPStatusError: If page not found or API error.
            ValueError: If no extract available.
        """
        encoded = quote(query.replace(" ", "_"))
        url = f"{_SEARCH_URL}/{encoded}"

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                url,
                params={"redirect": "true"},
                headers={"Accept": "application/json", "User-Agent": "NEXUS-Tool-Agent/1.0"},
                follow_redirects=True,
            )

            if response.status_code == 404:
                # Try with search redirect
                response = await client.get(
                    url,
                    params={"redirect": "true"},
                    headers={"Accept": "application/json"},
                    follow_redirects=True,
                )

            response.raise_for_status()
            data = response.json()

        title: str = data.get("title", query)
        extract: str = data.get("extract", "")
        page_url: str = data.get("content_urls", {}).get("desktop", {}).get("page", "")

        if not extract:
            raise ValueError(f"No extract available for '{query}'")

        # Truncate to first 500 chars for Kafka payload size limits
        summary = extract.rsplit(".", 1)[0] + "." if len(extract) > 500 else extract

        return title, summary, page_url
