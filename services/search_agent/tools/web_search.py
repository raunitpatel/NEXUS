
from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from typing import TypedDict

import httpx
import structlog

logger = structlog.get_logger(__name__)


# Shared Result Schema

class SearchResult(TypedDict):
    title: str
    url: str
    snippet: str
    relevance_score: float


# Base Provider Interface

class BaseSearchProvider(ABC):

    @abstractmethod
    async def search(
        self,
        query: str,
    ) -> list[SearchResult]:
        pass


# Tavily Provider

class TavilySearchProvider(BaseSearchProvider):

    def __init__(
        self,
        api_key: str,
        max_results: int = 5,
    ) -> None:

        self._api_key = api_key
        self._max_results = max_results

        self._url = "https://api.tavily.com/search"

    async def search(
        self,
        query: str,
    ) -> list[SearchResult]:

        logger.info(
            "tavily.search.start",
            query=query[:100],
        )

        payload = {
            "api_key": self._api_key,
            "query": query,
            "search_depth": "advanced",
            "include_answer": False,
            "include_raw_content": False,
            "max_results": self._max_results,
        }

        async with httpx.AsyncClient(
            timeout=15.0,
        ) as client:

            response = await client.post(
                self._url,
                json=payload,
            )

            response.raise_for_status()

            data = response.json()

        results: list[SearchResult] = []

        for item in data.get("results", []):

            results.append(
                {
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "snippet": item.get("content", ""),
                    "relevance_score": 0.0,
                }
            )

        logger.info(
            "tavily.search.complete",
            count=len(results),
        )

        return results


# Mock Provider

# Mock Provider

class MockSearchProvider(BaseSearchProvider):

    def __init__(
        self,
        max_results: int = 5,
    ) -> None:
        self._max_results = max_results

    async def search(
        self,
        query: str,
    ) -> list[SearchResult]:

        await asyncio.sleep(0.2)

        results: list[SearchResult] = [
            {
                "title": f"Overview: {query[:40]}",
                "url": "https://example.com/overview",
                "snippet": (
                    f"A comprehensive overview of {query[:60]}. "
                    "This resource covers key concepts, recent developments, "
                    "and practical applications in the field."
                ),
                "relevance_score": 0,
            },
            {
                "title": f"Deep dive: {query[:35]} — Research Paper",
                "url": "https://arxiv.org/abs/mock-2024-001",
                "snippet": (
                    f"This paper presents novel findings related to {query[:50]}. "
                    "Authors propose a new framework that outperforms prior baselines "
                    "on standard benchmarks by 12% across five metrics."
                ),
                "relevance_score": 0.0,
            },
            {
                "title": f"Practical guide to {query[:40]}",
                "url": "https://towardsdatascience.com/mock-guide",
                "snippet": (
                    f"Step-by-step walkthrough for implementing {query[:50]}. "
                    "Includes code examples, common pitfalls, and performance tips "
                    "for production deployments."
                ),
                "relevance_score": 0.0,
            },
            {
                "title": f"{query[:45]} — Wikipedia",
                "url": f"https://en.wikipedia.org/wiki/{query[:30].replace(' ', '_')}",
                "snippet": (
                    f"{query[:60]} is a concept in computer science and AI research. "
                    "It encompasses various techniques and methodologies used in "
                    "modern machine learning systems."
                ),
                "relevance_score": 0.0,
            },
            {
                "title": f"Latest news on {query[:40]}",
                "url": "https://techcrunch.com/mock-news",
                "snippet": (
                    f"Industry developments in {query[:50]} as of 2024. "
                    "Major technology companies have announced new initiatives "
                    "and open-source releases in this space."
                ),
                "relevance_score": 0.0,
            },
        ]

        return results[: self._max_results]

# Main Tool Wrapper

class WebSearchTool:
    """
    Provider-agnostic web search tool.
    """

    def __init__(
        self,
        provider: str,
        api_key: str = "",
        max_results: int = 5,
    ) -> None:

        self._provider = self._build_provider(
            provider=provider,
            api_key=api_key,
            max_results=max_results,
        )

    def _build_provider(
        self,
        provider: str,
        api_key: str,
        max_results: int,
    ) -> BaseSearchProvider:

        provider = provider.lower()

        if provider == "tavily":
            return TavilySearchProvider(
                api_key=api_key,
                max_results=max_results,
            )

        if provider == "mock":
            return MockSearchProvider(
                max_results=max_results,
            )

        raise ValueError(
            f"Unsupported provider: {provider}"
        )

    async def search(
        self,
        query: str,
    ) -> list[SearchResult]:

        logger.info(
            "web_search.query",
            query=query[:100],
        )

        results = await self._provider.search(
            query,
        )

        logger.info(
            "web_search.results",
            count=len(results),
        )

        return results