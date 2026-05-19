# services/orchestrator/nodes/validate_plan.py
"""
validate_plan node — validates the task plan from decompose_query before execution.

Checks:
  1. Plan is non-empty (1–6 tasks)
  2. All agent_type values are in the NEXUS allowed set
  3. depends_on indices are valid integers within range and form a DAG (no cycles)

On failure, sets state["error"] and returns — graph routes to handle_error.
On success, returns {} (no state change needed).
"""

from __future__ import annotations

from typing import Any

import structlog

from state import OrchestratorState

logger = structlog.get_logger(__name__)

_VALID_AGENT_TYPES = frozenset({
    "search", "code", "memory_read", "memory_write", "tool",
})


def _detect_cycle(adjacency: dict[int, list[int]]) -> bool:
    """
    Detect a cycle in a directed graph using iterative DFS with a recursion stack.

    Safe for up to 6 nodes (max plan size) — no stack overflow risk.

    Args:
        adjacency: Dict mapping node index to list of dependency indices.

    Returns:
        True if a cycle exists, False otherwise.
    """
    visited: set[int] = set()
    in_stack: set[int] = set()

    def dfs(node: int) -> bool:
        visited.add(node)
        in_stack.add(node)
        for neighbour in adjacency.get(node, []):
            if neighbour not in visited:
                if dfs(neighbour):
                    return True
            elif neighbour in in_stack:
                return True
        in_stack.discard(node)
        return False

    for node in adjacency:
        if node not in visited:
            if dfs(node):
                return True
    return False


async def validate_plan(state: OrchestratorState) -> dict[str, Any]:
    """
    Validate the task plan produced by decompose_query.

    Sets state["error"] and returns early if the plan is invalid so the
    graph routes to handle_error. Returns {} on success (no state change).

    Args:
        state: Current OrchestratorState with task_plan populated.

    Returns:
        Partial state dict. Sets "error" and "status" keys on validation failure,
        empty dict on success.
    """
    run_id = state["run_id"]
    task_plan = state.get("task_plan", [])

    logger.info("node.validate_plan.start", run_id=run_id, task_count=len(task_plan))

    if not task_plan:
        msg = "Task plan is empty — decompose_query produced no tasks."
        logger.warning("node.validate_plan.empty_plan", run_id=run_id)
        return {"error": msg, "status": "failed"}

    if len(task_plan) > 6:
        msg = f"Task plan has {len(task_plan)} tasks — maximum is 6."
        logger.warning("node.validate_plan.too_many_tasks", run_id=run_id)
        return {"error": msg, "status": "failed"}

    for i, task in enumerate(task_plan):
        agent_type = task.get("agent_type", "")
        if agent_type not in _VALID_AGENT_TYPES:
            msg = f"Task {i} has invalid agent_type '{agent_type}'."
            logger.warning(
                "node.validate_plan.invalid_agent_type",
                run_id=run_id,
                task_index=i,
                agent_type=agent_type,
            )
            return {"error": msg, "status": "failed"}

    n = len(task_plan)
    adjacency: dict[int, list[int]] = {i: [] for i in range(n)}

    for i, task in enumerate(task_plan):
        for dep in task.get("depends_on", []):
            try:
                dep_idx = int(dep)
            except (ValueError, TypeError):
                msg = f"Task {i} depends_on contains non-integer value '{dep}'."
                return {"error": msg, "status": "failed"}
            if dep_idx < 0 or dep_idx >= n:
                msg = (
                    f"Task {i} depends_on index {dep_idx} is out of range "
                    f"(plan has {n} tasks)."
                )
                return {"error": msg, "status": "failed"}
            if dep_idx == i:
                msg = f"Task {i} has a self-dependency."
                return {"error": msg, "status": "failed"}
            adjacency[i].append(dep_idx)

    if _detect_cycle(adjacency):
        msg = "Task plan contains a cyclic dependency."
        logger.warning("node.validate_plan.cycle_detected", run_id=run_id)
        return {"error": msg, "status": "failed"}

    logger.info("node.validate_plan.success", run_id=run_id, task_count=n)
    return {"task_plan": state["task_plan"]}