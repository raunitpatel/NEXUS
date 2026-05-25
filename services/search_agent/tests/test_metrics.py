"""
Unit tests for AGNT-017 metric instrumentation in SearchAgent.run().

Run:
    docker exec nexus-search-agent python -m pytest tests/test_metrics.py -v --asyncio-mode=auto
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from llm_provider import LLMResponse


def _mock_llm(content: str) -> MagicMock:
    r = MagicMock()
    r.content = content
    r.prompt_tokens = 100
    r.completion_tokens = 50
    r.cache_hit = False
    return r


@pytest.mark.asyncio
async def test_search_agent_records_task_duration_on_success() -> None:
    """agent_task_duration_seconds.observe() called with status=success on successful run."""
    from agent import SearchAgent

    rerank_json = json.dumps([{"index": i, "score": 0.5} for i in range(5)])
    mock_provider = AsyncMock()
    mock_provider.complete = AsyncMock(
        side_effect=[
            _mock_llm("query"),
            _mock_llm(rerank_json),
            _mock_llm("summary"),
        ]
    )

    mock_duration = MagicMock()
    mock_tasks_total = MagicMock()

    with (
        patch("agent.CachedLLMProvider", return_value=mock_provider),
        patch("agent.SearchAgent._publish_event", new_callable=AsyncMock),
        patch("agent.agent_task_duration_seconds", mock_duration),
        patch("agent.agent_tasks_total", mock_tasks_total),
    ):
        agent = SearchAgent(redis_client=AsyncMock())
        await agent.run(task_id="t1", run_id="r1", user_id="u1", query="test")

    mock_duration.labels(agent="search", status="success").observe.assert_called_once()
    mock_tasks_total.labels(agent="search", status="success").inc.assert_called_once()


@pytest.mark.asyncio
async def test_search_agent_records_task_duration_on_llm_error() -> None:
    """agent_task_duration_seconds.observe() called with status=error on LLMProviderError."""
    from agent import SearchAgent
    from llm_provider import LLMProviderError

    mock_provider = AsyncMock()
    mock_provider.complete = AsyncMock(side_effect=LLMProviderError("claude", "timeout"))

    mock_duration = MagicMock()
    mock_tasks_total = MagicMock()

    with (
        patch("agent.CachedLLMProvider", return_value=mock_provider),
        patch("agent.SearchAgent._publish_event", new_callable=AsyncMock),
        patch("agent.agent_task_duration_seconds", mock_duration),
        patch("agent.agent_tasks_total", mock_tasks_total),
    ):
        agent = SearchAgent(redis_client=AsyncMock())
        await agent.run(task_id="t1", run_id="r1", user_id="u1", query="test")

    mock_duration.labels(agent="search", status="error").observe.assert_called_once()
    mock_tasks_total.labels(agent="search", status="error").inc.assert_called_once()
