# services/orchestrator/tests/test_graph.py
"""Unit tests for graph.py — graph compilation and all conditional edge routers."""

import pytest

from graph import (
    _route_after_await,
    _route_after_error,
    _route_after_record,
    _route_after_validate,
    build_graph,
)
from state import OrchestratorState


def _base_state() -> OrchestratorState:
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
        "status": "running",
        "error": None,
        "input_tokens": 0,
        "output_tokens": 0,
        "metadata": {},
    }


def _make_task_plan(task_id: str = "t1") -> dict:
    return {
        "task_id": task_id,
        "agent_type": "search",
        "task_type": "search",
        "agent_url": "http://search-agent:8002",
        "input": {"query": "test"},
        "depends_on": [],
    }


def _make_task_result(task_id: str = "t1", error: str | None = None) -> dict:
    return {
        "task_id": task_id,
        "agent_type": "search",
        "output": {"results": []},
        "error": error,
        "duration_ms": 1200,
        "attempt": 1,
    }


# ── Graph compilation ────────────────────────────────────────────────────────


def test_build_graph_compiles_without_error() -> None:
    """build_graph() returns a compiled graph object without raising."""
    graph = build_graph()
    assert graph is not None


def test_draw_mermaid_contains_all_eight_nodes() -> None:
    """draw_mermaid() output contains all 8 node names."""
    graph = build_graph()
    mermaid = graph.get_graph().draw_mermaid()

    expected_nodes = [
        "decompose_query",
        "validate_plan",
        "dispatch_next_task",
        "await_task_result",
        "record_result",
        "synthesize_output",
        "finalize_run",
        "handle_error",
    ]
    for node in expected_nodes:
        assert node in mermaid, f"Node '{node}' missing from Mermaid diagram"


# ── _route_after_validate ────────────────────────────────────────────────────


def test_route_validate_empty_plan_routes_to_handle_error() -> None:
    """Empty task_plan routes to handle_error — correct for stub decompose_query."""
    assert _route_after_validate(_base_state()) == "handle_error"


def test_route_validate_with_error_set_routes_to_handle_error() -> None:
    """Error on state routes to handle_error even if task_plan is populated."""
    state = {**_base_state(), "task_plan": [_make_task_plan()], "error": "llm failed"}
    assert _route_after_validate(state) == "handle_error"  # type: ignore[arg-type]


def test_route_validate_valid_plan_routes_to_dispatch() -> None:
    """Populated task_plan with no error routes to dispatch_next_task."""
    state = {**_base_state(), "task_plan": [_make_task_plan()]}
    assert _route_after_validate(state) == "dispatch_next_task"  # type: ignore[arg-type]


# ── _route_after_await ───────────────────────────────────────────────────────


def test_route_await_task_error_routes_to_handle_error() -> None:
    """task_result with error routes to handle_error."""
    state = {**_base_state(), "task_result": _make_task_result(error="timeout")}
    assert _route_after_await(state) == "handle_error"  # type: ignore[arg-type]


def test_route_await_task_ok_routes_to_record_result() -> None:
    """task_result with no error routes to record_result."""
    state = {**_base_state(), "task_result": _make_task_result()}
    assert _route_after_await(state) == "record_result"  # type: ignore[arg-type]


def test_route_await_no_task_result_routes_to_record_result() -> None:
    """None task_result (stub) routes to record_result — no error means success."""
    assert _route_after_await(_base_state()) == "record_result"


# ── _route_after_record ──────────────────────────────────────────────────────


def test_route_record_more_tasks_routes_to_dispatch() -> None:
    """1 completed out of 2 tasks routes to dispatch_next_task."""
    state = {
        **_base_state(),
        "task_plan": [_make_task_plan("t1"), _make_task_plan("t2")],
        "completed_tasks": [_make_task_result("t1")],
    }
    assert _route_after_record(state) == "dispatch_next_task"  # type: ignore[arg-type]


def test_route_record_all_done_routes_to_synthesize() -> None:
    """All tasks completed routes to synthesize_output."""
    state = {
        **_base_state(),
        "task_plan": [_make_task_plan("t1")],
        "completed_tasks": [_make_task_result("t1")],
    }
    assert _route_after_record(state) == "synthesize_output"  # type: ignore[arg-type]


# ── _route_after_error ───────────────────────────────────────────────────────


def test_route_error_within_retries_routes_to_dispatch() -> None:
    """retry_count=1 with max_plan_retries=3 routes to dispatch_next_task."""
    state = {**_base_state(), "retry_count": 1}
    assert _route_after_error(state) == "dispatch_next_task"


def test_route_error_at_max_retries_routes_to_finalize() -> None:
    """retry_count=3 with max_plan_retries=3 routes to finalize_run."""
    state = {**_base_state(), "retry_count": 3}
    assert _route_after_error(state) == "finalize_run"


def test_route_error_beyond_max_retries_routes_to_finalize() -> None:
    """retry_count > max_plan_retries also routes to finalize_run."""
    state = {**_base_state(), "retry_count": 5}
    assert _route_after_error(state) == "finalize_run"