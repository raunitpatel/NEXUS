"""
dispatch_next_task node — sends the next pending task to the appropriate agent via Kafka.

Stub implementation returns state unchanged.
AGNT-009 replaces the stub body with:
  - Selecting the next unstarted task from task_plan (tasks not in completed_tasks)
  - Producing a TaskDispatchedEvent to nexus.tasks Kafka topic
  - Setting pending_task on state
"""

import structlog

from state import OrchestratorState

logger = structlog.get_logger(__name__)


async def dispatch_next_task(state: OrchestratorState) -> OrchestratorState:
    """Pick the next unstarted task from task_plan and dispatch it via Kafka.

    Args:
        state: Current OrchestratorState with task_plan and completed_tasks populated.

    Returns:
        Updated state with pending_task set. Stub returns unchanged.
    """
    logger.info("node.dispatch_next_task.stub", run_id=state["run_id"])
    # --- AGNT-009: Kafka producer call replaces this stub ---
    return state