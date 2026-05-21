"""
handle_error node — records failure, increments retry_count, decides retry vs. abort.

The conditional edge _route_after_error in graph.py reads retry_count against
settings.max_plan_retries to decide whether to re-enter dispatch_next_task
or route to finalize_run. This node must correctly increment retry_count so
that routing logic works even with stub implementations everywhere else.
"""

import structlog

from state import OrchestratorState
from sqlalchemy.ext.asyncio import AsyncEngine
from nodes import _redis_client
from sse_emitter import emit_event

_db_engine: AsyncEngine | None = None
def set_db_engine(engine: AsyncEngine) -> None:
    global _db_engine
    _db_engine = engine

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

    # Insert error event row if DB is available
    if _db_engine is not None:
        try:
            import json
            from sqlalchemy import text
            from sqlalchemy.ext.asyncio import async_sessionmaker
            session_factory = async_sessionmaker(
                bind=_db_engine,
                expire_on_commit=False,
                autoflush=False,
            )
            async with session_factory() as session:
                await session.execute(
                    text(
                        """
                        INSERT INTO events (run_id, type, payload, source)
                        VALUES (:run_id, 'run_error', CAST(:payload AS jsonb), 'orchestrator.handle_error')
                        """
                    ),
                    {
                        "run_id": run_id,
                        "payload": json.dumps({
                            "error": error_msg,
                            "retry_count": current_retry,
                        }),
                    },
                )
                await session.commit()
        except Exception as exc:
            logger.error("node.handle_error.db_error", run_id=run_id, error=str(exc))
    
    try:
        if _redis_client is not None:
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