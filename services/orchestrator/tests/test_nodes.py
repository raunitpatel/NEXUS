# services/orchestrator/tests/test_nodes.py
"""
Unit tests for all 8 orchestrator node stub functions.

Each node is tested in isolation with a minimal OrchestratorState.
No external dependencies — all stubs are pure functions.
Token counter fields (input_tokens, output_tokens) are included in the
fixture because AGNT-008 node implementations will read and increment them.
"""

import pytest

from state import OrchestratorState


def _base_state() -> OrchestratorState:
    """Return a minimal valid OrchestratorState for testing."""
    return {
        "run_id": "test-run-001",
        "user_id": "test-user-001",
        "query": "test query",
        "task_plan": [],
        "completed_tasks": [],
        "pending_task": None,
        "task_result": None,
        "retry_count": 0,
        "final_output": None,
        "status": "pending",
        "error": None,
        "input_tokens": 0,
        "output_tokens": 0,
        "metadata": {},
    }


@pytest.mark.asyncio
async def test_decompose_query_stub_sets_running_status() -> None:
    """decompose_query stub sets status='running' and returns empty task_plan."""
    from nodes.decompose_query import decompose_query

    result = await decompose_query(_base_state())

    assert result["status"] == "running"
    assert result["task_plan"] == []
    assert result["run_id"] == "test-run-001"


@pytest.mark.asyncio
async def test_validate_plan_stub_returns_state_unchanged() -> None:
    """validate_plan stub returns state unchanged."""
    from nodes.validate_plan import validate_plan

    state = _base_state()
    result = await validate_plan(state)

    assert result == state


@pytest.mark.asyncio
async def test_dispatch_next_task_stub_returns_state_unchanged() -> None:
    """dispatch_next_task stub returns state unchanged."""
    from nodes.dispatch_next_task import dispatch_next_task

    state = _base_state()
    result = await dispatch_next_task(state)

    assert result == state


@pytest.mark.asyncio
async def test_await_task_result_stub_returns_state_unchanged() -> None:
    """await_task_result stub returns state unchanged."""
    from nodes.await_task_result import await_task_result

    state = _base_state()
    result = await await_task_result(state)

    assert result == state


@pytest.mark.asyncio
async def test_record_result_stub_returns_state_unchanged() -> None:
    """record_result stub returns state unchanged."""
    from nodes.record_result import record_result

    state = _base_state()
    result = await record_result(state)

    assert result == state


@pytest.mark.asyncio
async def test_synthesize_output_stub_sets_completed_and_empty_output() -> None:
    """synthesize_output stub sets status='completed' and final_output=''."""
    from nodes.synthesize_output import synthesize_output

    result = await synthesize_output(_base_state())

    assert result["status"] == "completed"
    assert result["final_output"] == ""


@pytest.mark.asyncio
async def test_finalize_run_stub_returns_state_unchanged() -> None:
    """finalize_run stub returns state unchanged."""
    from nodes.finalize_run import finalize_run

    state = _base_state()
    result = await finalize_run(state)

    assert result == state


@pytest.mark.asyncio
async def test_handle_error_increments_retry_count() -> None:
    """handle_error increments retry_count by 1 and sets status='failed'."""
    from nodes.handle_error import handle_error

    state = {**_base_state(), "retry_count": 1, "error": "search timeout"}
    result = await handle_error(state)

    assert result["retry_count"] == 2
    assert result["status"] == "failed"


@pytest.mark.asyncio
async def test_handle_error_starts_from_zero() -> None:
    """handle_error on first error sets retry_count=1."""
    from nodes.handle_error import handle_error

    state = {**_base_state(), "error": "llm parse error"}
    result = await handle_error(state)

    assert result["retry_count"] == 1
    assert result["status"] == "failed"