"""
Search Agent core — chains three LLM calls to search and summarize.

Three-step pipeline:
  1. formulate_query  — LLM rewrites raw query into optimal search terms
  2. web_search       — calls WebSearchTool (stub in AGNT-010, real in AGNT-024)
  3. rerank_and_summarize — LLM scores results by relevance and produces summary

All LLM calls go through CachedLLMProvider (Redis SHA-256 cache, 3600s TTL).
Kafka agent_end event published to nexus.events on completion or failure.

Usage:
    agent = SearchAgent(redis_client=app.state.redis)
    result = await agent.run(task_id="t1", run_id="r1", user_id="u1", query="...")
"""

from __future__ import annotations

import json
import time
from typing import Any

from shared.metrics import (
    agent_task_duration_seconds,
    agent_tasks_total,
    llm_tokens_total,
    llm_requests_total,
)

import structlog

from cached_llm_provider import CachedLLMProvider
from config import settings
from llm_provider import LLMProviderError, get_llm_provider
from tools.web_search import SearchResult, WebSearchTool

logger = structlog.get_logger(__name__)

# ── System prompts ────────────────────────────────────────────────────────────

_FORMULATE_SYSTEM = """\
You are a search query optimization assistant. Your job is to rewrite a user's
raw question into an optimal search query string for a web search engine.

Rules:
1. Return ONLY the search query string — no explanation, no quotes, no punctuation.
2. Keep it under 12 words.
3. Include the most specific technical terms from the user's question.
4. Remove filler words (what is, how to, can you, please, etc.).

Examples:
User: "What are the latest papers on transformer attention mechanisms?"
Output: transformer attention mechanisms 2024 research papers

User: "How do I implement pgvector similarity search in Python?"
Output: pgvector cosine similarity search Python asyncpg implementation
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
    """
    Return value from SearchAgent.run().

    Attributes:
        results: Re-ranked list of SearchResult dicts (highest score first).
        summary: LLM-generated summary answering the user's query.
        tokens_used: Total tokens consumed across all three LLM calls.
        cache_hits: Number of LLM calls served from Redis cache.
        duration_ms: Wall-clock time for the full pipeline in milliseconds.
    """

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
        """Serialise to a dict suitable for JSON response and Kafka payload."""
        return {
            "results": list(self.results),
            "summary": self.summary,
            "tokens_used": self.tokens_used,
            "cache_hits": self.cache_hits,
            "duration_ms": self.duration_ms,
        }


class SearchAgent:
    """
    NEXUS Search Agent — query formulation, web search, and summarization.

    All LLM calls are routed through CachedLLMProvider for Redis-backed caching.
    Publishes agent_start and agent_end events to nexus.events Kafka topic.

    Attributes:
        _cached_provider: CachedLLMProvider wrapping the configured LLMProvider.
        _search_tool: WebSearchTool instance.
    """

    def __init__(self, redis_client: Any) -> None:
        """
        Initialise the Search Agent with a Redis client for LLM caching.

        Args:
            redis_client: Async Redis client from app.state.redis.
        """
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
        """Return the active model name from config for use in cache keys."""
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
        """
        Execute the full search pipeline for a given query.

        Chains: formulate_query → web_search → rerank_and_summarize.
        Publishes agent_start and agent_end Kafka events.
        On any LLMProviderError, sets empty results and error summary.

        Args:
            task_id: UUID of the task row in Postgres tasks table.
            run_id: UUID of the parent orchestration run.
            user_id: UUID of the authenticated user (for Kafka event).
            query: Raw user query string from OrchestratorState.

        Returns:
            SearchAgentResult with results, summary, and token counts.
        """
        start_ms = time.monotonic()
        total_tokens = 0
        cache_hits = 0

        await self._publish_event(
            run_id=run_id,
            task_id=task_id,
            event_type="agent_start",
            payload={"query": query[:200], "agent": "search"},
        )

        try:
            # Step 1: Formulate optimal search query
            formulated_query, tokens, hit = await self._formulate_query(query)
            total_tokens += tokens
            cache_hits += int(hit)

            # Step 2: Execute web search
            raw_results = await self._search_tool.search(formulated_query)

            # Step 3: Re-rank results
            ranked_results, tokens, hit = await self._rerank(query, raw_results)
            total_tokens += tokens
            cache_hits += int(hit)

            # Step 4: Summarize top results
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
        llm_tokens_total.labels(service="search-agent", model=model_name, type="input").inc(
            total_tokens  # approximate — full breakdown requires per-call tracking
        )
        llm_requests_total.labels(service="search-agent", model=model_name, status="success").inc(3)
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
            cache_hits=cache_hits,
            duration_ms=elapsed,
        )
        return result

    async def _formulate_query(self, raw_query: str) -> tuple[str, int, bool]:
        """
        Rewrite the raw user query into optimal search terms.

        Args:
            raw_query: The original user query string.

        Returns:
            Tuple of (formulated_query_string, tokens_used, cache_hit).
        """
        response = await self._cached_provider.complete(
            system=_FORMULATE_SYSTEM,
            user=f"Rewrite this query for web search:\n\n{raw_query}",
        )
        formulated = response.content.strip().strip('"')
        tokens = response.prompt_tokens + response.completion_tokens
        logger.debug("search_agent.formulate_query", formulated=formulated, cache_hit=response.cache_hit)
        return formulated, tokens, response.cache_hit

    async def _rerank(
        self,
        original_query: str,
        results: list[SearchResult],
    ) -> tuple[list[SearchResult], int, bool]:
        """
        Score each search result for relevance and return sorted list.

        Args:
            original_query: The user's original query (not formulated).
            results: Raw search results from WebSearchTool.

        Returns:
            Tuple of (sorted_results_high_to_low, tokens_used, cache_hit).
        """
        results_text = "\n".join(
            f"[{i}] Title: {r['title']}\nSnippet: {r['snippet']}"
            for i, r in enumerate(results)
        )
        user_msg = (
            f"Original query: {original_query}\n\n"
            f"Search results to rank:\n{results_text}"
        )
        response = await self._cached_provider.complete(
            system=_RERANK_SYSTEM,
            user=user_msg,
            json_mode=True,
        )
        tokens = response.prompt_tokens + response.completion_tokens

        # Parse scores and apply to results
        try:
            scores: list[dict] = json.loads(response.content)
            score_map = {item["index"]: item["score"] for item in scores}
        except (json.JSONDecodeError, KeyError, TypeError):
            logger.warning("search_agent.rerank_parse_error", raw=response.content[:200])
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
        """
        Generate a prose summary answering the query from top-ranked results.

        Args:
            original_query: The user's original query.
            ranked_results: Results sorted by relevance (highest first).

        Returns:
            Tuple of (summary_string, tokens_used, cache_hit).
        """
        top_results = ranked_results[:3]
        results_text = "\n".join(
            f"[{i+1}] {r['title']}: {r['snippet']}"
            for i, r in enumerate(top_results)
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
        """
        Publish an agent event to nexus.events Kafka topic.

        Failures are logged and swallowed — must not abort the agent run.

        Args:
            run_id: Parent orchestration run UUID.
            task_id: Task UUID.
            event_type: One of 'agent_start', 'agent_end'.
            payload: Arbitrary event data.
        """
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