"""
Search Agent — internal module for the NEXUS Orchestrator.

Previously a standalone FastAPI service (services/search_agent/).
Now a direct Python import used by nodes/dispatch_next_task.py.

Three-step pipeline:
  1. formulate_query  — LLM rewrites raw query into optimal search terms
  2. web_search       — calls WebSearchTool
  3. rerank_and_summarize — LLM scores results and produces summary
"""

from __future__ import annotations

import json
import time
from typing import Any

import structlog
from shared.metrics import (
    agent_task_duration_seconds,
    agent_tasks_total,
    llm_requests_total,
    llm_tokens_total,
)

from .cached_llm_provider import CachedLLMProvider
from .tools.web_search import SearchResult, WebSearchTool

logger = structlog.get_logger(__name__)

_FORMULATE_SYSTEM = """\
You are a search query optimization assistant. Your job is to rewrite a user's
raw question into an optimal search query string for a web search engine.

Rules:
1. Return ONLY the search query string — no explanation, no quotes, no punctuation.
2. Keep it under 12 words.
3. Include the most specific technical terms from the user's question.
4. Remove filler words (what is, how to, can you, please, etc.).
"""

_RERANK_SYSTEM = """\
You are a search result relevance ranker. Given a user's original query and a list
of search results, score each result for relevance to the query.

Rules:
1. Return ONLY valid JSON — no prose, no markdown, no code fences.
2. Return an array of objects with exactly two keys: "index" (int) and "score" (float 0.0–1.0).
3. Score 1.0 = perfectly relevant, 0.0 = completely irrelevant.
4. Preserve original ordering — index 0 is the first result.

Example output:
[{"index": 0, "score": 0.9}, {"index": 1, "score": 0.4}, {"index": 2, "score": 0.7}]
"""

_SUMMARIZE_SYSTEM = """\
You are a research summarizer. Given a user's query and the top-ranked search results,
produce a concise, accurate summary that directly answers the user's question.

Rules:
1. Write 2–4 sentences of dense, informative prose.
2. Cite sources as [1], [2], etc. referencing result order.
3. Do not pad with filler or meta-commentary.
4. If results are insufficient, say so briefly.
"""


class SearchAgentResult:
    """Return value from SearchAgent.run()."""

    def __init__(
        self,
        results: list[SearchResult],
        summary: str,
        tokens_used: int,
        cache_hits: int,
        duration_ms: int,
    ) -> None:
        self.results = results
        self.summary = summary
        self.tokens_used = tokens_used
        self.cache_hits = cache_hits
        self.duration_ms = duration_ms

    def to_dict(self) -> dict[str, Any]:
        return {
            "results": list(self.results),
            "summary": self.summary,
            "tokens_used": self.tokens_used,
            "cache_hits": self.cache_hits,
            "duration_ms": self.duration_ms,
        }


class SearchAgent:
    """
    NEXUS Search Agent — internal Python class, not a FastAPI service.

    Called directly from nodes/dispatch_next_task.py.
    """

    def __init__(self, redis_client: Any) -> None:
        from llm_provider import get_llm_provider
        from config import settings

        base_provider = get_llm_provider()
        self._cached_provider = CachedLLMProvider(
            base_provider=base_provider,
            redis_client=redis_client,
            model=self._model_name(),
            ttl_seconds=settings.llm_cache_ttl_seconds,
        )
        self._search_tool = WebSearchTool(
            provider=settings.search_provider,
            api_key=settings.tavily_api_key,
            max_results=settings.search_max_results,
        )

    def _model_name(self) -> str:
        from config import settings
        provider = settings.llm_provider.lower()
        if provider == "claude":
            return settings.anthropic_model
        if provider == "gemini":
            return settings.gemini_model
        return settings.ollama_model

    async def run(
        self,
        task_id: str,
        run_id: str,
        user_id: str,
        query: str,
    ) -> SearchAgentResult:
        """Execute the full search pipeline."""
        from llm_provider import LLMProviderError

        start_ms = time.monotonic()
        total_tokens = 0
        cache_hits = 0

        await self._publish_event(
            run_id=run_id,
            task_id=task_id,
            event_type="agent_start",
            payload={"query": query, "agent": "search"},
        )

        try:
            formulated_query, tokens, hit = await self._formulate_query(query)
            total_tokens += tokens
            cache_hits += int(hit)

            raw_results = await self._search_tool.search(formulated_query)

            ranked_results, tokens, hit = await self._rerank(query, raw_results)
            total_tokens += tokens
            cache_hits += int(hit)

            summary, tokens, hit = await self._summarize(query, ranked_results)
            total_tokens += tokens
            cache_hits += int(hit)

        except LLMProviderError as exc:
            logger.error("search_agent.llm_error", run_id=run_id, task_id=task_id, error=str(exc))
            elapsed = int((time.monotonic() - start_ms) * 1000)
            agent_task_duration_seconds.labels(agent="search", status="error").observe(elapsed / 1000)
            agent_tasks_total.labels(agent="search", status="error").inc()
            result = SearchAgentResult(
                results=[],
                summary=f"Search failed: LLM provider error — {exc}",
                tokens_used=total_tokens,
                cache_hits=cache_hits,
                duration_ms=elapsed,
            )
            await self._publish_event(
                run_id=run_id,
                task_id=task_id,
                event_type="agent_end",
                payload={**result.to_dict(), "error": str(exc)},
            )
            return result

        elapsed = int((time.monotonic() - start_ms) * 1000)
        agent_task_duration_seconds.labels(agent="search", status="success").observe(elapsed / 1000)
        agent_tasks_total.labels(agent="search", status="success").inc()
        model_name = self._model_name()
        llm_tokens_total.labels(service="orchestrator", model=model_name, type="input").inc(total_tokens)
        llm_requests_total.labels(service="orchestrator", model=model_name, status="success").inc(3)

        result = SearchAgentResult(
            results=ranked_results,
            summary=summary,
            tokens_used=total_tokens,
            cache_hits=cache_hits,
            duration_ms=elapsed,
        )
        await self._publish_event(
            run_id=run_id,
            task_id=task_id,
            event_type="agent_end",
            payload=result.to_dict(),
        )
        logger.info(
            "search_agent.run_complete",
            run_id=run_id,
            task_id=task_id,
            tokens=total_tokens,
            duration_ms=elapsed,
        )
        return result

    async def _formulate_query(self, raw_query: str) -> tuple[str, int, bool]:
        response = await self._cached_provider.complete(
            system=_FORMULATE_SYSTEM,
            user=f"Rewrite this query for web search:\n\n{raw_query}",
        )
        formulated = response.content.strip().strip('"')
        tokens = response.prompt_tokens + response.completion_tokens
        return formulated, tokens, response.cache_hit

    async def _rerank(
        self,
        original_query: str,
        results: list[SearchResult],
    ) -> tuple[list[SearchResult], int, bool]:
        results_text = "\n".join(
            f"[{i}] Title: {r['title']}\nSnippet: {r['snippet']}" for i, r in enumerate(results)
        )
        user_msg = f"Original query: {original_query}\n\nSearch results to rank:\n{results_text}"
        response = await self._cached_provider.complete(
            system=_RERANK_SYSTEM,
            user=user_msg,
            json_mode=True,
        )
        tokens = response.prompt_tokens + response.completion_tokens
        try:
            scores: list[dict] = json.loads(response.content)
            score_map = {item["index"]: item["score"] for item in scores}
        except (json.JSONDecodeError, KeyError, TypeError):
            score_map = {}

        ranked = list(results)
        for i, result in enumerate(ranked):
            result["relevance_score"] = float(score_map.get(i, 0.5))
        ranked.sort(key=lambda r: r["relevance_score"], reverse=True)
        return ranked, tokens, response.cache_hit

    async def _summarize(
        self,
        original_query: str,
        ranked_results: list[SearchResult],
    ) -> tuple[str, int, bool]:
        top_results = ranked_results[:3]
        results_text = "\n".join(
            f"[{i + 1}] {r['title']}: {r['snippet']}" for i, r in enumerate(top_results)
        )
        user_msg = (
            f"User query: {original_query}\n\n"
            f"Top search results:\n{results_text}\n\n"
            "Provide a concise answer citing these sources."
        )
        response = await self._cached_provider.complete(
            system=_SUMMARIZE_SYSTEM,
            user=user_msg,
        )
        tokens = response.prompt_tokens + response.completion_tokens
        return response.content.strip(), tokens, response.cache_hit

    async def _publish_event(
        self,
        run_id: str,
        task_id: str,
        event_type: str,
        payload: dict[str, Any],
    ) -> None:
        from config import settings
        from shared.kafka_client import KafkaProducerFactory
        from shared.kafka_schemas import EventMessage

        try:
            producer = await KafkaProducerFactory.get_producer(
                bootstrap_servers=settings.kafka_bootstrap_servers
            )
            event = EventMessage(
                run_id=run_id,
                task_id=task_id,
                event_type=event_type,  # type: ignore[arg-type]
                source="search_agent.agent",
                payload=payload,
            )
            await producer.send(
                settings.kafka_topic_events,
                value=event.model_dump_json().encode(),
            )
        except Exception as exc:
            logger.warning(
                "search_agent.kafka_publish_failed",
                run_id=run_id,
                task_id=task_id,
                error=str(exc),
            )