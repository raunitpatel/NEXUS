"""
await_task_result node — polls Kafka nexus.results for the dispatched task result.

Stub implementation returns state unchanged.
AGNT-009 replaces the stub body with:
  - asyncio.wait_for(consumer.getone(), timeout=settings.task_timeout_seconds)
  - Deserializing the Kafka message into TaskResult
  - Setting task_result on state
  - Raising TaskTimeoutError on timeout (routed to handle_error)
"""

import structlog

from state import OrchestratorState

logger = structlog.get_logger(__name__)


async def await_task_result(state: OrchestratorState) -> OrchestratorState:
    """Block until the agent returns a result for the current pending_task.

    Args:
        state: Current OrchestratorState with pending_task set.

    Returns:
        Updated state with task_result populated. Stub returns unchanged.
    """
    logger.info("node.await_task_result.stub", run_id=state["run_id"])
    # --- AGNT-009: Kafka consumer with asyncio.wait_for replaces this stub ---
    return state