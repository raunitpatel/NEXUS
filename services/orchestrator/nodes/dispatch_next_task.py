"""
dispatch_next_task node — selects the next executable task and dispatches it
via DIRECT PYTHON CALLS to internal agent modules.

In the hybrid Railway architecture, agents are no longer standalone FastAPI
services. They are Python classes in services/orchestrator/agents/ called
directly, eliminating inter-service HTTP overhead.

On agent error, sets state["error"] — graph routes to handle_error.
"""

from __future__ import annotations

import time
from typing import Any

import structlog
from sse_emitter import emit_event
from state import OrchestratorState, TaskPlan

from nodes import get_redis_client
from nodes.task_persistence import task_exists

logger = structlog.get_logger(__name__)


def _select_next_task(
    task_plan: list[TaskPlan],
    completed_tasks: list[Any],
) -> TaskPlan | None:
    """Select the first task from task_plan not yet in completed_tasks."""
    completed_ids = {t["task_id"] for t in completed_tasks}
    for task in task_plan:
        if task["task_id"] not in completed_ids:
            return task
    return None


def _remap_input_for_agent(
    agent_type: str,
    raw_input: dict[str, Any],
) -> dict[str, Any]:
    """Remap task input keys to match each agent's expected parameter names."""
    description = raw_input.get("description", raw_input.get("query", ""))
    query = raw_input.get("query", description)

    if agent_type == "search":
        return {"query": query}
    if agent_type == "code":
        return {"instruction": description, "language": "python"}
    if agent_type == "memory_read":
        return {"query": query}
    if agent_type == "memory_write":
        return {"content": description, "content_type": "task_output"}
    if agent_type == "tool":
        return {"instruction": description}
    return raw_input


async def _call_search_agent(
    task_id: str,
    run_id: str,
    user_id: str,
    agent_input: dict[str, Any],
) -> dict[str, Any]:
    """Call SearchAgent directly as a Python class."""
    from nodes.app_state import get_redis_client as _get_redis
    from agents.search_agent import SearchAgent

    redis_client = _get_redis()
    if redis_client is None:
        raise RuntimeError("Redis client not available for SearchAgent")

    agent = SearchAgent(redis_client=redis_client)
    result = await agent.run(
        task_id=task_id,
        run_id=run_id,
        user_id=user_id,
        query=agent_input.get("query", ""),
    )
    return {"output": result.to_dict(), "error": None}


async def _call_code_agent(
    task_id: str,
    run_id: str,
    user_id: str,
    agent_input: dict[str, Any],
) -> dict[str, Any]:
    """Call CodeAgent directly as a Python class."""
    from agents.code_agent import CodeAgent

    agent = CodeAgent()
    result = await agent.run(
        task_id=task_id,
        run_id=run_id,
        user_id=user_id,
        instruction=agent_input.get("instruction", ""),
        language=agent_input.get("language", "python"),
    )
    error = None if result.success else "Code execution failed after max iterations"
    return {"output": result.to_dict(), "error": error}


async def _call_memory_agent(
    task_id: str,
    run_id: str,
    user_id: str,
    agent_input: dict[str, Any],
    task_type: str,
) -> dict[str, Any]:
    """Call MemoryAgent directly as a Python class."""
    from nodes.app_state import get_db_pool, get_redis_client as _get_redis
    from agents.memory_agent import MemoryAgent

    db_pool = get_db_pool()
    redis_client = _get_redis()
    if db_pool is None:
        raise RuntimeError("DB pool not available for MemoryAgent")
    if redis_client is None:
        raise RuntimeError("Redis client not available for MemoryAgent")

    agent = MemoryAgent(db_pool=db_pool, redis_client=redis_client)

    if task_type == "memory_write":
        content = agent_input.get("content", "")
        if not content:
            return {"output": None, "error": "input.content is required for memory_write"}
        result = await agent.embed(
            run_id=run_id,
            content=content,
            content_type=agent_input.get("content_type", "task_output"),
            task_id=task_id,
            user_id=user_id,
        )
        return {"output": result.to_dict(), "error": None}
    else:
        query = agent_input.get("query", "")
        if not query:
            return {"output": None, "error": "input.query is required for memory_read"}
        result = await agent.search(
            user_id=user_id,
            query_text=query,
            limit=agent_input.get("limit"),
            similarity_threshold=agent_input.get("similarity_threshold"),
        )
        return {"output": result.to_dict(), "error": None}


async def _call_tool_agent(
    task_id: str,
    run_id: str,
    user_id: str,
    agent_input: dict[str, Any],
) -> dict[str, Any]:
    """Call ToolAgent directly as a Python class."""
    from nodes.app_state import get_db_engine
    from agents.tool_agent import ToolAgent

    db_engine = get_db_engine()
    agent = ToolAgent(db_engine=db_engine)
    result = await agent.run(
        task_id=task_id,
        run_id=run_id,
        user_id=user_id,
        instruction=agent_input.get("instruction", ""),
    )
    return {"output": result.to_dict(), "error": result.error}


async def dispatch_next_task(state: OrchestratorState) -> dict[str, Any]:
    """
    Select and dispatch the next pending task via direct Python agent calls.
    """
    run_id = state["run_id"]
    task_plan = state.get("task_plan", [])
    completed_tasks = state.get("completed_tasks", [])
    attempt = state.get("retry_count", 0) + 1

    next_task = _select_next_task(task_plan, completed_tasks)

    if next_task is None:
        logger.warning("node.dispatch_next_task.no_task_to_dispatch", run_id=run_id)
        return {"error": "dispatch_next_task called but no pending tasks remain."}

    agent_type: str = next_task["agent_type"]
    task_id = next_task["task_id"]

    try:
        if not await task_exists(task_id):
            msg = f"Task {task_id} does not exist in the tasks table before dispatch."
            logger.error("node.dispatch_next_task.missing_task_record", run_id=run_id, task_id=task_id)
            return {"error": msg}
    except Exception as exc:
        logger.error("node.dispatch_next_task.task_existence_check_failed", run_id=run_id, error=str(exc))
        return {"error": str(exc)}

    raw_input = next_task.get("input", {})
    agent_input = _remap_input_for_agent(agent_type, raw_input)

    logger.info(
        "node.dispatch_next_task.dispatching",
        run_id=run_id,
        task_id=task_id,
        agent_type=agent_type,
        dispatch_mode="direct_python",
    )

    start_ms = time.monotonic()

    try:
        if agent_type == "search":
            response_data = await _call_search_agent(task_id, run_id, state["user_id"], agent_input)
        elif agent_type == "code":
            response_data = await _call_code_agent(task_id, run_id, state["user_id"], agent_input)
        elif agent_type in ("memory_read", "memory_write"):
            response_data = await _call_memory_agent(
                task_id, run_id, state["user_id"], agent_input, agent_type
            )
        elif agent_type == "tool":
            response_data = await _call_tool_agent(task_id, run_id, state["user_id"], agent_input)
        else:
            return {"error": f"Unknown agent_type '{agent_type}'"}

    except Exception as exc:
        elapsed = int((time.monotonic() - start_ms) * 1000)
        msg = f"Agent {agent_type} raised exception after {elapsed}ms: {exc}"
        logger.error("node.dispatch_next_task.agent_exception", run_id=run_id, agent_type=agent_type, error=str(exc))
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
        task_id=task_id,
        agent_type=agent_type,
        elapsed_ms=elapsed_ms,
        dispatch_mode="direct_python",
    )

    try:
        _redis_client = get_redis_client()
        if _redis_client is not None:
            await emit_event(
                run_id=run_id,
                event_type="orchestrator_dispatch",
                agent_name="orchestrator.dispatch_next_task",
                payload={
                    "task_id": task_id,
                    "agent_type": agent_type,
                    "dispatch_mode": "direct_python",
                },
                redis_client=_redis_client,
            )
    except Exception as _exc:
        logger.warning("dispatch_next_task.emit_failed", run_id=run_id, error=str(_exc))

    return {"pending_task": pending_task_with_response}