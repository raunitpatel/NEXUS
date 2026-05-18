"""
finalize_run node — writes terminal state to Postgres runs table and emits run_complete event.

Stub implementation returns state unchanged.
AGNT-010 replaces the stub body with:
  - UPDATE runs SET status=state["status"], output=state["final_output"],
    completed_at=NOW(), metadata=state["metadata"] WHERE id=state["run_id"]
  - PUBLISH run_complete event to Redis pub/sub channel run:{run_id}:events
  - INSERT into events table with type='run_complete' or 'run_error'
"""

import structlog

from state import OrchestratorState

logger = structlog.get_logger(__name__)


async def finalize_run(state: OrchestratorState) -> OrchestratorState:
    """Update runs.status, runs.output, runs.completed_at in Postgres and emit SSE event.

    Args:
        state: Current OrchestratorState with final_output or error set.

    Returns:
        State unchanged — this is a terminal node with no further routing.
    """
    logger.info(
        "node.finalize_run.stub",
        run_id=state["run_id"],
        status=state.get("status"),
    )
    # --- AGNT-010: DB UPDATE and Redis PUBLISH replaces this stub ---
    return state