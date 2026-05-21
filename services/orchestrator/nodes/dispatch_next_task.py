"""
dispatch_next_task node — selects the next executable task and dispatches it via HTTP.

Selects the first TaskPlan from task_plan whose task_id is not already in
completed_tasks. Resolves the agent service URL from config. Fires a POST
to {agent_url}/run with a JSON payload. Stores the raw response dict and
dispatch metadata on state["pending_task"].

On HTTP error or timeout, sets state["error"] — graph routes to handle_error.
"""

from __future__ import annotations

import time
from typing import Any

import httpx
import structlog

from state import OrchestratorState, TaskPlan
from nodes import _redis_client
from sse_emitter import emit_event

logger = structlog.get_logger(__name__)


def _resolve_agent_url(agent_type: str) -> str:
    """
    Resolve the internal Docker service URL for the given agent_type.

    Reads from config.settings — never hardcodes URLs.

    Args:
        agent_type: One of search/code/memory_read/memory_write/tool/synthesize.

    Returns:
        Base URL string (e.g. "http://search-agent:8002").

    Raises:
        ValueError: If agent_type does not map to a known service.
    """
    from config import settings

    mapping: dict[str, str] = {
        "search": settings.search_agent_url,
        "code": settings.code_agent_url,
        "memory_read": settings.memory_agent_url,
        "memory_write": settings.memory_agent_url,
        "tool": settings.tool_agent_url,
    }
    url = mapping.get(agent_type)
    if not url:
        raise ValueError(
            f"No agent URL configured for agent_type='{agent_type}'. "
            f"Known types: {list(mapping.keys())}"
        )
    return url


def _select_next_task(
    task_plan: list[TaskPlan],
    completed_tasks: list[Any],
) -> TaskPlan | None:
    """
    Select the first task from task_plan not yet in completed_tasks.

    Dependency resolution (depends_on) is intentionally deferred to AGNT-013
    (parallel dispatch). For the MVP, tasks execute sequentially in plan order.

    Args:
        task_plan: Full list of planned tasks.
        completed_tasks: Tasks already finished (success or recorded failure).

    Returns:
        The next TaskPlan to dispatch, or None if all tasks are complete.
    """
    completed_ids = {t["task_id"] for t in completed_tasks}
    for task in task_plan:
        if task["task_id"] not in completed_ids:
            return task
    return None


async def dispatch_next_task(state: OrchestratorState) -> dict[str, Any]:
    """
    Select and dispatch the next pending task to the appropriate agent service.

    Fires a POST /{agent_url}/run and stores the response in pending_task.
    On timeout or HTTP error, sets state["error"] for handle_error routing.

    Args:
        state: Current OrchestratorState with task_plan and completed_tasks.

    Returns:
        Partial state dict with pending_task set, or error set on failure.
    """
    from config import settings

    run_id = state["run_id"]
    task_plan = state.get("task_plan", [])
    completed_tasks = state.get("completed_tasks", [])
    attempt = state.get("retry_count", 0) + 1

    next_task = _select_next_task(task_plan, completed_tasks)

    if next_task is None:
        logger.warning("node.dispatch_next_task.no_task_to_dispatch", run_id=run_id)
        return {"error": "dispatch_next_task called but no pending tasks remain."}

    agent_type: str = next_task["agent_type"]

    try:
        agent_url = _resolve_agent_url(agent_type)
    except ValueError as exc:
        logger.error("node.dispatch_next_task.unknown_agent_type", run_id=run_id, error=str(exc))
        return {"error": str(exc)}

    payload = {
        "run_id": run_id,
        "task_id": next_task["task_id"],
        "user_id": state["user_id"],
        "task_type": next_task.get("task_type", agent_type),
        "input": next_task.get("input", {}),
        "attempt": attempt,
    }

    logger.info(
        "node.dispatch_next_task.dispatching",
        run_id=run_id,
        task_id=next_task["task_id"],
        agent_type=agent_type,
        agent_url=agent_url,
    )

    start_ms = time.monotonic()

    try:
        async with httpx.AsyncClient(timeout=float(settings.task_timeout_seconds)) as client:
            response = await client.post(f"{agent_url}/run", json=payload)
            response.raise_for_status()
            response_data: dict[str, Any] = response.json()

    except httpx.TimeoutException:
        elapsed = int((time.monotonic() - start_ms) * 1000)
        msg = f"Agent {agent_type} timed out after {elapsed}ms (limit: {settings.task_timeout_seconds}s)."
        logger.warning("node.dispatch_next_task.timeout", run_id=run_id, agent_type=agent_type, elapsed_ms=elapsed)
        return {"error": msg}

    except httpx.HTTPStatusError as exc:
        msg = f"Agent {agent_type} returned HTTP {exc.response.status_code}: {exc.response.text[:200]}"
        logger.warning("node.dispatch_next_task.http_error", run_id=run_id, status=exc.response.status_code)
        return {"error": msg}

    except httpx.RequestError as exc:
        msg = f"Agent {agent_type} unreachable: {exc}"
        logger.error("node.dispatch_next_task.connection_error", run_id=run_id, error=str(exc))
        return {"error": msg}

    elapsed_ms = int((time.monotonic() - start_ms) * 1000)

    pending_task_with_response: dict[str, Any] = {
        **next_task,
        "_response": response_data,
        "_elapsed_ms": elapsed_ms,
        "_attempt": attempt,
    }

    logger.info(
        "node.dispatch_next_task.success",
        run_id=run_id,
        task_id=next_task["task_id"],
        agent_type=agent_type,
        elapsed_ms=elapsed_ms,
    )

    try:
        if _redis_client is not None:
            await emit_event(
                run_id=run_id,
                event_type="orchestrator_dispatch",
                agent_name="orchestrator.dispatch_next_task",
                payload={
                    "task_id": next_task["task_id"],
                    "agent_type": agent_type,
                    "agent_url": agent_url,
                },
                redis_client=_redis_client,
            )
    except Exception as _exc:
        logger.warning("dispatch_next_task.emit_failed", run_id=run_id, error=str(_exc))

    return {"pending_task": pending_task_with_response}