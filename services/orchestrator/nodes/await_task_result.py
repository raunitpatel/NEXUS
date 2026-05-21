# services/orchestrator/nodes/await_task_result.py
"""
await_task_result node — normalises the agent HTTP response into a TaskResult.

In the MVP synchronous HTTP model, the agent response is already stored in
state["pending_task"]["_response"] by dispatch_next_task. This node reads
that response and constructs a normalised TaskResult TypedDict.

If pending_task is None (should not happen given the new conditional edge after
dispatch_next_task, but guarded defensively), sets state["error"].

AGNT-013 upgrades this to consume from Kafka nexus.results with asyncio.wait_for.
"""

from __future__ import annotations

from typing import Any

import structlog

from state import OrchestratorState, TaskResult
from nodes import _redis_client

logger = structlog.get_logger(__name__)


async def await_task_result(state: OrchestratorState) -> dict[str, Any]:
    """
    Normalise the agent response stored in pending_task into a TaskResult.

    Reads _response, _elapsed_ms, and _attempt from pending_task.
    Sets state["task_result"] with the normalised output.
    Sets state["error"] if the response indicates task failure so
    _route_after_await routes to handle_error.

    Args:
        state: Current OrchestratorState with pending_task populated by
               dispatch_next_task.

    Returns:
        Partial state dict with task_result set (and optionally error set).
    """
    run_id = state["run_id"]
    pending_task = state.get("pending_task")

    if not pending_task:
        # Defensive guard — the conditional edge after dispatch_next_task should
        # prevent reaching here with no pending_task, but guard anyway.
        msg = "await_task_result called but pending_task is None."
        logger.error("node.await_task_result.no_pending_task", run_id=run_id)
        return {"error": msg}

    task_id: str = pending_task["task_id"]
    agent_type: str = pending_task["agent_type"]
    response_data: dict[str, Any] = pending_task.get("_response", {})
    elapsed_ms: int = pending_task.get("_elapsed_ms", 0)
    attempt: int = pending_task.get("_attempt", 1)

    # Agent services return {"output": {...}, "error": null | "error message"}
    output: dict[str, Any] = response_data.get("output") or {}
    agent_error: str | None = response_data.get("error")

    task_result: TaskResult = {
        "task_id": task_id,
        "agent_type": agent_type,      # type: ignore[typeddict-item]
        "output": output,
        "error": agent_error,
        "duration_ms": elapsed_ms,
        "attempt": attempt,
    }

    if agent_error:
        logger.warning(
            "node.await_task_result.agent_error",
            run_id=run_id,
            task_id=task_id,
            agent_type=agent_type,
            error=agent_error,
        )
        return {"task_result": task_result, "error": agent_error}

    logger.info(
        "node.await_task_result.success",
        run_id=run_id,
        task_id=task_id,
        agent_type=agent_type,
        duration_ms=elapsed_ms,
    )

    return {"task_result": task_result}