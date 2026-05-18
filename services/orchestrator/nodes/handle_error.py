"""
handle_error node — records failure, increments retry_count, decides retry vs. abort.

The conditional edge _route_after_error in graph.py reads retry_count against
settings.max_plan_retries to decide whether to re-enter dispatch_next_task
or route to finalize_run. This node must correctly increment retry_count so
that routing logic works even with stub implementations everywhere else.
"""

import structlog

from state import OrchestratorState

logger = structlog.get_logger(__name__)


async def handle_error(state: OrchestratorState) -> OrchestratorState:
    """Increment retry_count and set status='failed'.

    Args:
        state: Current OrchestratorState with error set by the failing node.

    Returns:
        Updated state with retry_count incremented by 1 and status='failed'.
    """
    current_retry = state.get("retry_count", 0)
    logger.warning(
        "node.handle_error",
        run_id=state["run_id"],
        error=state.get("error"),
        retry_count=current_retry,
    )
    # --- AGNT-010: DB error event INSERT replaces stub logging ---
    return {
        **state,
        "retry_count": current_retry + 1,
        "status": "failed",
    }