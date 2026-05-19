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

        "task_plan": [],
        "completed_tasks": [],
        "pending_task": None,
        "task_result": None,

        "final_output": None,

        "status": "running",
        "error": None,
        "retry_count": 0,

        "input_tokens": 0,
        "output_tokens": 0,

        "metadata": {},
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

    assert "task_plan" in result
    plan = result["task_plan"]
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

        result = await decompose_query(_base_state(input_tokens=50, output_tokens=20))

    assert result["input_tokens"] == 200
    assert result["output_tokens"] == 80


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
            attempt=1,
        )
    ]

    with (
        patch("nodes.synthesize_output.get_llm_provider", return_value=mock_provider),
        patch("nodes.synthesize_output._publish_llm_response_event", new_callable=AsyncMock),
    ):
        from nodes.synthesize_output import synthesize_output

        result = await synthesize_output(_base_state(completed_tasks=task_results))

    assert result["final_output"] == synthesis_text
    assert result["input_tokens"] == 300
    assert result["output_tokens"] == 120


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

# ---------------------------------------------------------------------------
# validate_plan tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_validate_plan_empty_plan_returns_error() -> None:
    """validate_plan with empty task_plan returns error key."""
    from nodes.validate_plan import validate_plan

    result = await validate_plan(_base_state(task_plan=[]))
    assert "error" in result
    assert "empty" in result["error"].lower()


@pytest.mark.asyncio
async def test_validate_plan_invalid_agent_type_returns_error() -> None:
    """validate_plan with unknown agent_type sets error."""
    from nodes.validate_plan import validate_plan

    bad_plan = [{
        "task_id": "t1", "agent_type": "browser",
        "task_type": "browser", "agent_url": "", "input": {}, "depends_on": [],
    }]
    result = await validate_plan(_base_state(task_plan=bad_plan))
    assert "error" in result
    assert "browser" in result["error"]


@pytest.mark.asyncio
async def test_validate_plan_cycle_returns_error() -> None:
    """validate_plan with cyclic depends_on sets error."""
    from nodes.validate_plan import validate_plan

    cyclic_plan = [
        {"task_id": "t1", "agent_type": "search", "task_type": "search",
        "agent_url": "", "input": {}, "depends_on": ["1"]},
        {"task_id": "t2", "agent_type": "tool", "task_type": "tool",
        "agent_url": "", "input": {}, "depends_on": ["0"]},
    ]
    result = await validate_plan(_base_state(task_plan=cyclic_plan))
    assert "error" in result
    assert "cyclic" in result["error"].lower()


@pytest.mark.asyncio
async def test_validate_plan_valid_returns_empty_dict() -> None:
    """validate_plan with valid DAG plan returns empty dict (no changes)."""
    from nodes.validate_plan import validate_plan

    valid_plan = [
        {"task_id": "t1", "agent_type": "search", "task_type": "search",
        "agent_url": "http://search-agent:8002", "input": {}, "depends_on": []},
        {"task_id": "t2", "agent_type": "synthesize", "task_type": "synthesize",
        "agent_url": "", "input": {}, "depends_on": ["0"]},
    ]
    result = await validate_plan(_base_state(task_plan=valid_plan))
    assert result["task_plan"] == valid_plan


# ---------------------------------------------------------------------------
# dispatch_next_task tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_dispatch_next_task_posts_to_correct_url() -> None:
    """dispatch_next_task POSTs to the agent URL and sets pending_task."""
    from unittest.mock import AsyncMock, MagicMock, patch
    from nodes.dispatch_next_task import dispatch_next_task

    task_plan = [{
        "task_id": "t1", "agent_type": "search", "task_type": "search",
        "agent_url": "http://search-agent:8002", "input": {"query": "test"}, "depends_on": [],
    }]

    mock_response = MagicMock()
    mock_response.json.return_value = {"output": {"results": ["r1"]}, "error": None}
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_response)

    with patch("nodes.dispatch_next_task.httpx.AsyncClient", return_value=mock_client):
        result = await dispatch_next_task(_base_state(task_plan=task_plan))

    assert "pending_task" in result
    assert result["pending_task"]["task_id"] == "t1"
    assert result["pending_task"]["_response"]["output"]["results"] == ["r1"]
    mock_client.post.assert_awaited_once()
    call_url = mock_client.post.call_args[0][0]
    assert "search-agent" in call_url


@pytest.mark.asyncio
async def test_dispatch_next_task_timeout_sets_error() -> None:
    """dispatch_next_task on timeout sets state error."""
    from unittest.mock import AsyncMock, patch
    import httpx
    from nodes.dispatch_next_task import dispatch_next_task

    task_plan = [{
        "task_id": "t1", "agent_type": "search", "task_type": "search",
        "agent_url": "http://search-agent:8002", "input": {}, "depends_on": [],
    }]

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("timeout"))

    with patch("nodes.dispatch_next_task.httpx.AsyncClient", return_value=mock_client):
        result = await dispatch_next_task(_base_state(task_plan=task_plan))

    assert "error" in result
    assert "timed out" in result["error"].lower()


@pytest.mark.asyncio
async def test_dispatch_next_task_skips_completed() -> None:
    """dispatch_next_task skips tasks already in completed_tasks."""
    from unittest.mock import AsyncMock, MagicMock, patch
    from nodes.dispatch_next_task import dispatch_next_task

    task_plan = [
        {"task_id": "t1", "agent_type": "search", "task_type": "search",
        "agent_url": "http://search-agent:8002", "input": {}, "depends_on": []},
        {"task_id": "t2", "agent_type": "tool", "task_type": "tool",
        "agent_url": "http://tool-agent:8005", "input": {}, "depends_on": []},
    ]
    completed = [{"task_id": "t1", "agent_type": "search", "output": {}, "error": None, "duration_ms": 100, "attempt": 1}]

    mock_response = MagicMock()
    mock_response.json.return_value = {"output": {}, "error": None}
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_response)

    with patch("nodes.dispatch_next_task.httpx.AsyncClient", return_value=mock_client):
        result = await dispatch_next_task(_base_state(task_plan=task_plan, completed_tasks=completed))

    assert result["pending_task"]["task_id"] == "t2"
    call_url = mock_client.post.call_args[0][0]
    assert "tool-agent" in call_url


# ---------------------------------------------------------------------------
# await_task_result tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_await_task_result_normalises_success_response() -> None:
    """await_task_result builds TaskResult from pending_task._response."""
    from nodes.await_task_result import await_task_result

    pending = {
        "task_id": "t1", "agent_type": "search", "task_type": "search",
        "agent_url": "http://search-agent:8002", "input": {}, "depends_on": [],
        "_response": {"output": {"results": ["r1"]}, "error": None},
        "_elapsed_ms": 1200, "_attempt": 1,
    }
    result = await await_task_result(_base_state(pending_task=pending))

    assert result["task_result"]["task_id"] == "t1"
    assert result["task_result"]["error"] is None
    assert result["task_result"]["duration_ms"] == 1200
    assert "error" not in result or result.get("error") is None


@pytest.mark.asyncio
async def test_await_task_result_propagates_agent_error() -> None:
    """await_task_result sets state error when agent response contains error."""
    from nodes.await_task_result import await_task_result

    pending = {
        "task_id": "t1", "agent_type": "search", "task_type": "search",
        "agent_url": "http://search-agent:8002", "input": {}, "depends_on": [],
        "_response": {"output": None, "error": "search API unavailable"},
        "_elapsed_ms": 500, "_attempt": 1,
    }
    result = await await_task_result(_base_state(pending_task=pending))

    assert result["task_result"]["error"] == "search API unavailable"
    assert result["error"] == "search API unavailable"


# ---------------------------------------------------------------------------
# record_result tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_record_result_appends_to_completed_tasks() -> None:
    """record_result appends task_result and clears pending_task."""
    from unittest.mock import patch, AsyncMock
    from nodes.record_result import record_result

    task_result = {
        "task_id": "t1", "agent_type": "search", "output": {"results": []},
        "error": None, "duration_ms": 1000, "attempt": 1,
    }

    with patch("nodes.record_result._db_engine", None):  # skip DB
        result = await record_result(_base_state(task_result=task_result))

    assert len(result["completed_tasks"]) == 1
    assert result["completed_tasks"][0]["task_id"] == "t1"
    assert result["pending_task"] is None
    assert result["task_result"] is None


@pytest.mark.asyncio
async def test_record_result_executes_db_update() -> None:
    """record_result calls AsyncSession.execute with UPDATE when engine is set."""
    from unittest.mock import AsyncMock, MagicMock, patch
    from nodes.record_result import record_result

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    mock_factory = MagicMock(return_value=mock_session)
    mock_engine = MagicMock()

    task_result = {
        "task_id": "t1", "agent_type": "search", "output": {},
        "error": None, "duration_ms": 500, "attempt": 1,
    }

    with (
        patch("nodes.record_result._db_engine", mock_engine),
        patch("nodes.record_result.async_sessionmaker", return_value=mock_factory),
    ):
        await record_result(_base_state(task_result=task_result))

    mock_session.execute.assert_awaited_once()
    mock_session.commit.assert_awaited_once()


# ---------------------------------------------------------------------------
# finalize_run tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_finalize_run_sets_completed_status() -> None:
    """finalize_run returns status=completed when no error in state."""
    from unittest.mock import patch, AsyncMock, MagicMock
    from nodes.finalize_run import finalize_run

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    mock_factory = MagicMock(return_value=mock_session)
    mock_engine = MagicMock()

    with (
        patch("nodes.finalize_run._db_engine", mock_engine),
        patch("nodes.record_result._db_engine", mock_engine),
        patch("nodes.finalize_run.async_sessionmaker", return_value=mock_factory),
        patch("nodes.finalize_run._publish_run_event", new_callable=AsyncMock),
    ):
        result = await finalize_run(_base_state(final_output="The answer is 42."))

    assert result["status"] == "completed"


@pytest.mark.asyncio
async def test_finalize_run_sets_failed_status_on_error() -> None:
    """finalize_run returns status=failed when state has error."""
    from unittest.mock import patch, AsyncMock, MagicMock
    from nodes.finalize_run import finalize_run

    mock_engine = MagicMock()

    with (
        patch("nodes.finalize_run._db_engine", mock_engine),
        patch("nodes.record_result._db_engine", mock_engine),
        patch("nodes.finalize_run.async_sessionmaker", return_value=MagicMock(return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=AsyncMock(execute=AsyncMock(), commit=AsyncMock())),
            __aexit__=AsyncMock(return_value=False),
        ))),
        patch("nodes.finalize_run._publish_run_event", new_callable=AsyncMock),
    ):
        result = await finalize_run(_base_state(error="LLM provider failed"))

    assert result["status"] == "failed"