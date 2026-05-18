# services/orchestrator/tests/test_nodes.py
"""
Unit tests for orchestrator nodes: decompose_query and synthesize_output.

All external dependencies (LLMProvider, Kafka) are mocked.
No Docker containers required.

Run:
    cd nexus
    python -m pytest services/orchestrator/tests/test_nodes.py -v --asyncio-mode=auto
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from llm_provider import LLMResponse
from state import OrchestratorState, TaskResult


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _base_state(**overrides: Any) -> OrchestratorState:
    """Return a minimal OrchestratorState for testing."""
    state: OrchestratorState = {
        "run_id": "run_test_001",
        "user_id": "user_test_001",
        "query": "What are the latest papers on LLM reasoning?",
        "plan": [],
        "dispatched_task_ids": [],
        "task_results": [],
        "final_output": "",
        "status": "running",
        "error": None,
        "total_prompt_tokens": 0,
        "total_completion_tokens": 0,
    }
    state.update(overrides)  # type: ignore[typeddict-item]
    return state


def _mock_llm_response(content: str, prompt_tokens: int = 100, completion_tokens: int = 50) -> LLMResponse:
    """Return a fake LLMResponse."""
    return LLMResponse(
        content=content,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
    )


# ---------------------------------------------------------------------------
# decompose_query tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_decompose_query_returns_valid_plan() -> None:
    """decompose_query with valid LLM JSON returns state with list[TaskPlan]."""
    valid_plan_json = json.dumps({
        "tasks": [
            {"agent_type": "search", "description": "Find recent LLM reasoning papers", "depends_on": []},
            {"agent_type": "memory_read", "description": "Check prior research context", "depends_on": []},
            {"agent_type": "synthesize", "description": "Combine results", "depends_on": ["0", "1"]},
        ]
    })

    mock_provider = AsyncMock()
    mock_provider.complete = AsyncMock(
        return_value=_mock_llm_response(valid_plan_json, prompt_tokens=200, completion_tokens=80)
    )

    with (
        patch("nodes.decompose_query.get_llm_provider", return_value=mock_provider),
        patch("nodes.decompose_query._publish_thought_event", new_callable=AsyncMock),
    ):
        from nodes.decompose_query import decompose_query

        result = await decompose_query(_base_state())

    assert "plan" in result
    plan = result["plan"]
    assert len(plan) == 3
    assert plan[0]["agent_type"] == "search"
    assert plan[1]["agent_type"] == "memory_read"
    assert plan[2]["agent_type"] == "synthesize"
    assert all(t["task_id"] for t in plan)  # UUIDs assigned


@pytest.mark.asyncio
async def test_decompose_query_updates_token_counts() -> None:
    """decompose_query accumulates prompt and completion tokens on state."""
    valid_plan_json = json.dumps({
        "tasks": [
            {"agent_type": "tool", "description": "Calculate compound interest", "depends_on": []}
        ]
    })

    mock_provider = AsyncMock()
    mock_provider.complete = AsyncMock(
        return_value=_mock_llm_response(valid_plan_json, prompt_tokens=150, completion_tokens=60)
    )

    with (
        patch("nodes.decompose_query.get_llm_provider", return_value=mock_provider),
        patch("nodes.decompose_query._publish_thought_event", new_callable=AsyncMock),
    ):
        from nodes.decompose_query import decompose_query

        result = await decompose_query(_base_state(total_prompt_tokens=50, total_completion_tokens=20))

    assert result["total_prompt_tokens"] == 200   # 50 existing + 150 new
    assert result["total_completion_tokens"] == 80  # 20 existing + 60 new


@pytest.mark.asyncio
async def test_decompose_query_publishes_kafka_event() -> None:
    """decompose_query calls _publish_thought_event once."""
    valid_plan_json = json.dumps({
        "tasks": [
            {"agent_type": "search", "description": "Find info", "depends_on": []}
        ]
    })

    mock_provider = AsyncMock()
    mock_provider.complete = AsyncMock(return_value=_mock_llm_response(valid_plan_json))

    mock_publish = AsyncMock()

    with (
        patch("nodes.decompose_query.get_llm_provider", return_value=mock_provider),
        patch("nodes.decompose_query._publish_thought_event", mock_publish),
    ):
        from nodes.decompose_query import decompose_query
        await decompose_query(_base_state())

    mock_publish.assert_awaited_once()
    call_kwargs = mock_publish.call_args
    assert call_kwargs.kwargs["run_id"] == "run_test_001"


@pytest.mark.asyncio
async def test_decompose_query_raises_on_invalid_agent_type() -> None:
    """decompose_query raises OrchestratorError when LLM returns unknown agent_type."""
    bad_json = json.dumps({
        "tasks": [
            {"agent_type": "browser", "description": "Open Google", "depends_on": []}
        ]
    })

    mock_provider = AsyncMock()
    mock_provider.complete = AsyncMock(return_value=_mock_llm_response(bad_json))

    with (
        patch("nodes.decompose_query.get_llm_provider", return_value=mock_provider),
        patch("nodes.decompose_query._publish_thought_event", new_callable=AsyncMock),
    ):
        from nodes.decompose_query import decompose_query, OrchestratorError

        with pytest.raises(OrchestratorError, match="invalid task plan JSON"):
            await decompose_query(_base_state())


@pytest.mark.asyncio
async def test_decompose_query_raises_on_empty_plan() -> None:
    """decompose_query raises OrchestratorError when LLM returns 0 tasks."""
    empty_json = json.dumps({"tasks": []})

    mock_provider = AsyncMock()
    mock_provider.complete = AsyncMock(return_value=_mock_llm_response(empty_json))

    with (
        patch("nodes.decompose_query.get_llm_provider", return_value=mock_provider),
        patch("nodes.decompose_query._publish_thought_event", new_callable=AsyncMock),
    ):
        from nodes.decompose_query import decompose_query, OrchestratorError

        with pytest.raises(OrchestratorError, match="1–6 tasks"):
            await decompose_query(_base_state())


# ---------------------------------------------------------------------------
# synthesize_output tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_synthesize_output_sets_final_output() -> None:
    """synthesize_output sets non-empty final_output on state."""
    synthesis_text = "The latest LLM reasoning papers focus on chain-of-thought prompting..."

    mock_provider = AsyncMock()
    mock_provider.complete = AsyncMock(
        return_value=_mock_llm_response(synthesis_text, prompt_tokens=300, completion_tokens=120)
    )

    task_results: list[TaskResult] = [
        TaskResult(
            task_id="task-001",
            agent_type="search",
            output="Wei et al. 2022 chain-of-thought paper...",
            error=None,
            duration_ms=1200,
        )
    ]

    with (
        patch("nodes.synthesize_output.get_llm_provider", return_value=mock_provider),
        patch("nodes.synthesize_output._publish_llm_response_event", new_callable=AsyncMock),
    ):
        from nodes.synthesize_output import synthesize_output

        result = await synthesize_output(_base_state(task_results=task_results))

    assert result["final_output"] == synthesis_text
    assert result["total_prompt_tokens"] == 300
    assert result["total_completion_tokens"] == 120


@pytest.mark.asyncio
async def test_synthesize_output_publishes_kafka_event() -> None:
    """synthesize_output calls _publish_llm_response_event once with run_id."""
    mock_provider = AsyncMock()
    mock_provider.complete = AsyncMock(
        return_value=_mock_llm_response("Final answer here.")
    )
    mock_publish = AsyncMock()

    with (
        patch("nodes.synthesize_output.get_llm_provider", return_value=mock_provider),
        patch("nodes.synthesize_output._publish_llm_response_event", mock_publish),
    ):
        from nodes.synthesize_output import synthesize_output
        await synthesize_output(_base_state())

    mock_publish.assert_awaited_once()
    assert mock_publish.call_args.kwargs["run_id"] == "run_test_001"


@pytest.mark.asyncio
async def test_synthesize_output_raises_on_empty_llm_response() -> None:
    """synthesize_output raises OrchestratorError when LLM returns empty string."""
    mock_provider = AsyncMock()
    mock_provider.complete = AsyncMock(return_value=_mock_llm_response("   "))

    with (
        patch("nodes.synthesize_output.get_llm_provider", return_value=mock_provider),
        patch("nodes.synthesize_output._publish_llm_response_event", new_callable=AsyncMock),
    ):
        from nodes.synthesize_output import synthesize_output
        from nodes.decompose_query import OrchestratorError

        with pytest.raises(OrchestratorError, match="empty final_output"):
            await synthesize_output(_base_state())