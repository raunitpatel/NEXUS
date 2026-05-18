"""
record_result node — persists the completed TaskResult to Postgres and appends to completed_tasks.

Stub implementation returns state unchanged.
AGNT-010 replaces the stub body with:
  - INSERT into tool_results table
  - UPDATE tasks.status = 'completed'
  - Appending task_result to completed_tasks
  - Clearing pending_task
"""

import structlog

from state import OrchestratorState

logger = structlog.get_logger(__name__)


async def record_result(state: OrchestratorState) -> OrchestratorState:
    """Write the task_result to tool_results and tasks tables, append to completed_tasks.

    Args:
        state: Current OrchestratorState with task_result populated.

    Returns:
        Updated state with completed_tasks extended and pending_task cleared.
        Stub returns unchanged.
    """
    logger.info("node.record_result.stub", run_id=state["run_id"])
    # --- AGNT-010: DB write replaces this stub ---
    return state