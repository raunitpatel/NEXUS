"""
handle_error node — records failure, increments retry_count, decides retry vs. abort.

The conditional edge _route_after_error in graph.py reads retry_count against
settings.max_plan_retries to decide whether to re-enter dispatch_next_task
or route to finalize_run. This node must correctly increment retry_count so
that routing logic works even with stub implementations everywhere else.
"""

import structlog

from state import OrchestratorState
from nodes import get_redis_client
from sse_emitter import emit_event

logger = structlog.get_logger(__name__)

async def handle_error(state: OrchestratorState) -> OrchestratorState:
    """
    Increment retry_count, set status='failed', and insert an events row.

    Args:
        state: Current OrchestratorState with error set by the failing node.

    Returns:
        Updated state with retry_count incremented by 1 and status='failed'.
    """

    current_retry = state.get("retry_count", 0)
    run_id = state["run_id"]
    error_msg = state.get("error", "unknown error")

    logger.warning(
        "node.handle_error",
        run_id=run_id,
        error=error_msg,
        retry_count=current_retry,
    )

    # Event persistence is centralized in sse_emitter.emit_event(); this node
    # only emits the run_error event for delivery and persistence.
    
    try:
        _redis_client = get_redis_client()
        if _redis_client is None:
            logger.error(
                "dispach_next_task.redis_client_none",
                run_id=run_id,
                warning="SSE terminal event will NOT be delivered — _redis_client is None",
            )
        else:
            await emit_event(
                run_id=run_id,
                event_type="run_error",
                agent_name="orchestrator.handle_error",
                payload={"error": error_msg, "retry_count": current_retry + 1},
                redis_client=_redis_client,
            )
    except Exception as _exc:
        logger.warning("handle_error.emit_failed", run_id=run_id, error=str(_exc))
        
    return {
        **state,
        "retry_count": current_retry + 1,
        "status": "failed",
    }