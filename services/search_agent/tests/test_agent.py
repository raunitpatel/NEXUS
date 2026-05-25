"""
Unit tests for services/search_agent/agent.py and claude_client.py.

All external dependencies (LLM provider, Redis, Kafka) mocked via pytest-mock.
No Docker containers required.

Run:
    docker exec nexus-search-agent python -m pytest tests/ -v --asyncio-mode=auto
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from llm_provider import LLMResponse

# ── Fixtures ──────────────────────────────────────────────────────────────────


def _mock_llm_response(
    content: str, prompt_tokens: int = 100, completion_tokens: int = 50
) -> MagicMock:
    r = MagicMock()
    r.content = content
    r.prompt_tokens = prompt_tokens
    r.completion_tokens = completion_tokens
    r.cache_hit = False
    return r


def _mock_llm_response_cached(content: str) -> MagicMock:
    r = _mock_llm_response(content)
    r.cache_hit = True
    return r


# ── CachedLLMProvider tests ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cached_provider_cache_miss_calls_provider() -> None:
    """On cache miss, CachedLLMProvider calls base provider and writes to Redis."""
    from cached_llm_provider import CachedLLMProvider

    mock_provider = AsyncMock()
    mock_provider.complete = AsyncMock(
        return_value=LLMResponse(content="result", prompt_tokens=10, completion_tokens=5)
    )
    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value=None)  # cache miss
    mock_redis.set = AsyncMock(return_value=True)

    provider = CachedLLMProvider(
        base_provider=mock_provider,
        redis_client=mock_redis,
        model="claude-sonnet-4-20250514",
        ttl_seconds=3600,
    )
    response = await provider.complete(system="sys", user="user")

    assert response.content == "result"
    assert response.cache_hit is False
    mock_provider.complete.assert_awaited_once()
    mock_redis.set.assert_awaited_once()
    # Verify TTL is 3600
    set_args = mock_redis.set.call_args
    assert set_args[1]["ex"] == 3600


@pytest.mark.asyncio
async def test_cached_provider_cache_hit_skips_provider() -> None:
    """On cache hit, CachedLLMProvider returns cached data without calling provider."""
    from cached_llm_provider import CachedLLMProvider

    cached_data = json.dumps(
        {"content": "cached result", "prompt_tokens": 10, "completion_tokens": 5}
    )
    mock_provider = AsyncMock()
    mock_provider.complete = AsyncMock()

    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value=cached_data)

    provider = CachedLLMProvider(
        base_provider=mock_provider,
        redis_client=mock_redis,
        model="claude-sonnet-4-20250514",
        ttl_seconds=3600,
    )
    response = await provider.complete(system="sys", user="user")

    assert response.content == "cached result"
    assert response.cache_hit is True
    mock_provider.complete.assert_not_awaited()


@pytest.mark.asyncio
async def test_cached_provider_redis_failure_falls_through() -> None:
    """Redis failure on read causes cache miss path — provider is still called."""
    from cached_llm_provider import CachedLLMProvider

    mock_provider = AsyncMock()
    mock_provider.complete = AsyncMock(
        return_value=LLMResponse(content="live result", prompt_tokens=10, completion_tokens=5)
    )
    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(side_effect=Exception("Redis connection refused"))
    mock_redis.set = AsyncMock(side_effect=Exception("Redis connection refused"))

    provider = CachedLLMProvider(
        base_provider=mock_provider,
        redis_client=mock_redis,
        model="test-model",
        ttl_seconds=3600,
    )
    response = await provider.complete(system="sys", user="user")

    assert response.content == "live result"
    assert response.cache_hit is False
    mock_provider.complete.assert_awaited_once()


@pytest.mark.asyncio
async def test_cache_key_includes_model_and_prompts() -> None:
    """Cache keys differ when model, system, or user changes."""
    from cached_llm_provider import CachedLLMProvider

    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value=None)
    mock_redis.set = AsyncMock(return_value=True)
    mock_provider = AsyncMock()
    mock_provider.complete = AsyncMock(
        return_value=LLMResponse(content="x", prompt_tokens=1, completion_tokens=1)
    )

    p1 = CachedLLMProvider(mock_provider, mock_redis, "model-a", 3600)
    p2 = CachedLLMProvider(mock_provider, mock_redis, "model-b", 3600)

    key1 = p1._make_cache_key("sys", "user")
    key2 = p2._make_cache_key("sys", "user")
    key3 = p1._make_cache_key("different sys", "user")

    assert key1 != key2
    assert key1 != key3
    assert key1.startswith("llm:cache:")


# ── SearchAgent tests ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_search_agent_run_returns_summary() -> None:
    """SearchAgent.run() returns SearchAgentResult with non-empty summary."""
    from agent import SearchAgent

    rerank_json = json.dumps(
        [
            {"index": 0, "score": 0.9},
            {"index": 1, "score": 0.7},
            {"index": 2, "score": 0.5},
            {"index": 3, "score": 0.3},
            {"index": 4, "score": 0.1},
        ]
    )

    mock_cached_provider = AsyncMock()
    mock_cached_provider.complete = AsyncMock(
        side_effect=[
            _mock_llm_response("LLM reasoning 2024"),  # formulate_query
            _mock_llm_response(rerank_json),  # rerank
            _mock_llm_response("LLMs use chain-of-thought [1]."),  # summarize
        ]
    )

    mock_redis = AsyncMock()

    with (
        patch("agent.CachedLLMProvider", return_value=mock_cached_provider),
        patch("agent.SearchAgent._publish_event", new_callable=AsyncMock),
    ):
        agent = SearchAgent(redis_client=mock_redis)
        result = await agent.run(
            task_id="t1",
            run_id="r1",
            user_id="u1",
            query="How do LLMs reason?",
        )

    assert result.summary == "LLMs use chain-of-thought [1]."
    assert len(result.results) == 5
    assert result.tokens_used == (150 + 150 + 150)  # 3 calls × (100+50)
    assert result.cache_hits == 0


@pytest.mark.asyncio
async def test_search_agent_tokens_summed_across_calls() -> None:
    """tokens_used correctly sums prompt + completion across all 3 LLM calls."""
    from agent import SearchAgent

    rerank_json = json.dumps([{"index": i, "score": 0.5} for i in range(5)])

    mock_cached_provider = AsyncMock()
    call_responses = [
        _mock_llm_response("query", prompt_tokens=200, completion_tokens=10),
        _mock_llm_response(rerank_json, prompt_tokens=500, completion_tokens=30),
        _mock_llm_response("summary", prompt_tokens=300, completion_tokens=80),
    ]
    mock_cached_provider.complete = AsyncMock(side_effect=call_responses)

    with (
        patch("agent.CachedLLMProvider", return_value=mock_cached_provider),
        patch("agent.SearchAgent._publish_event", new_callable=AsyncMock),
    ):
        agent = SearchAgent(redis_client=AsyncMock())
        result = await agent.run(task_id="t1", run_id="r1", user_id="u1", query="test")

    assert result.tokens_used == (210 + 530 + 380)


@pytest.mark.asyncio
async def test_search_agent_llm_error_returns_error_summary() -> None:
    """LLMProviderError in formulate_query results in error summary, not exception."""
    from agent import SearchAgent
    from llm_provider import LLMProviderError

    mock_cached_provider = AsyncMock()
    mock_cached_provider.complete = AsyncMock(
        side_effect=LLMProviderError("claude", "Connection refused")
    )

    with (
        patch("agent.CachedLLMProvider", return_value=mock_cached_provider),
        patch("agent.SearchAgent._publish_event", new_callable=AsyncMock),
    ):
        agent = SearchAgent(redis_client=AsyncMock())
        result = await agent.run(task_id="t1", run_id="r1", user_id="u1", query="test")

    assert "Search failed" in result.summary
    assert result.results == []


@pytest.mark.asyncio
async def test_search_agent_publishes_agent_start_and_end_events() -> None:
    """SearchAgent.run() publishes exactly two events: agent_start and agent_end."""
    from agent import SearchAgent

    rerank_json = json.dumps([{"index": i, "score": 0.5} for i in range(5)])
    mock_cached_provider = AsyncMock()
    mock_cached_provider.complete = AsyncMock(
        side_effect=[
            _mock_llm_response("query"),
            _mock_llm_response(rerank_json),
            _mock_llm_response("summary"),
        ]
    )

    publish_calls: list[str] = []

    async def capture_publish(**kwargs: object) -> None:
        publish_calls.append(str(kwargs.get("event_type", "")))

    with (
        patch("agent.CachedLLMProvider", return_value=mock_cached_provider),
        patch("agent.SearchAgent._publish_event", side_effect=capture_publish),
    ):
        agent = SearchAgent(redis_client=AsyncMock())
        await agent.run(task_id="t1", run_id="r1", user_id="u1", query="test")

    assert publish_calls == ["agent_start", "agent_end"]


@pytest.mark.asyncio
async def test_search_agent_rerank_parse_error_uses_default_score() -> None:
    """If LLM returns invalid JSON for rerank, results use default 0.5 score."""
    from agent import SearchAgent

    mock_cached_provider = AsyncMock()
    mock_cached_provider.complete = AsyncMock(
        side_effect=[
            _mock_llm_response("query"),
            _mock_llm_response("NOT VALID JSON"),  # rerank fails to parse
            _mock_llm_response("summary"),
        ]
    )

    with (
        patch("agent.CachedLLMProvider", return_value=mock_cached_provider),
        patch("agent.SearchAgent._publish_event", new_callable=AsyncMock),
    ):
        agent = SearchAgent(redis_client=AsyncMock())
        result = await agent.run(task_id="t1", run_id="r1", user_id="u1", query="test")

    # All results should have default score of 0.5 — sort is stable
    assert all(r["relevance_score"] == 0.5 for r in result.results)
    assert result.summary == "summary"


# ── WebSearchTool tests ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_web_search_tool_returns_max_results() -> None:
    """WebSearchTool.search() returns exactly max_results items."""
    from tools.web_search import WebSearchTool

    tool = WebSearchTool(
        provider="mock",
        api_key="x",
        max_results=3,
    )
    results = await tool.search("test query")

    assert len(results) == 3


@pytest.mark.asyncio
async def test_web_search_tool_result_has_required_fields() -> None:
    """All SearchResult dicts have title, url, snippet, relevance_score."""
    from tools.web_search import WebSearchTool

    tool = WebSearchTool(
        provider="mock",
        api_key="x",
        max_results=3,
    )
    results = await tool.search("LLM reasoning")

    for r in results:
        assert "title" in r
        assert "url" in r
        assert "snippet" in r
        assert "relevance_score" in r
        assert r["relevance_score"] == 0.0  # before reranking


# ── main.py endpoint tests ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_run_endpoint_missing_query_returns_error() -> None:
    """POST /run with empty input.query returns RunResponse with error."""
    from fastapi.testclient import TestClient
    from main import app

    with TestClient(app) as client:
        response = client.post(
            "/run",
            json={
                "run_id": "r1",
                "task_id": "t1",
                "user_id": "u1",
                "task_type": "search",
                "input": {},
                "attempt": 1,
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert data["error"] == "input.query is required"
    assert data["output"] is None


@pytest.mark.asyncio
async def test_healthz_returns_ok() -> None:
    """GET /healthz returns 200 with status ok."""
    from fastapi.testclient import TestClient
    from main import app

    with TestClient(app) as client:
        response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
