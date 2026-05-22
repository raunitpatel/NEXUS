"""
finalize_run node — writes terminal state to Postgres and emits run_complete event.

Executes:
  - UPDATE runs SET status, output, error, completed_at, metadata WHERE id
  - INSERT INTO events (run_id, type, payload, source)
  - KafkaProducer.send(nexus.events, run_complete/run_error EventMessage)

DB engine is accessed via record_result.set_db_engine() reference.
"""

from __future__ import annotations

import json
from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
from state import OrchestratorState
from nodes import get_redis_client
from sse_emitter import emit_event
from shared.kafka_schemas import EventMessage
from nodes.db import get_db_engine

logger = structlog.get_logger(__name__)

# Use shared engine accessor from nodes.db

async def finalize_run(state: OrchestratorState) -> dict[str, Any]:
    """
    Update runs table to terminal status and emit SSE run_complete/run_error event.

    Reads final_output and error from state. Computes metadata including
    total tokens and task count. Publishes to nexus.events Kafka topic.

    Args:
        state: Current OrchestratorState after synthesize_output or handle_error.

    Returns:
        Partial state dict with status set to "completed" or "failed".
    """

    run_id = state["run_id"]
    final_output: str | None = state.get("final_output")
    error: str | None = state.get("error")
    completed_tasks = state.get("completed_tasks", [])

    terminal_status = "failed" if error else "completed"

    metadata = {
        "input_tokens": state.get("input_tokens", 0),
        "output_tokens": state.get("output_tokens", 0),
        "task_count": len(state.get("task_plan", [])),
        "completed_task_count": len(completed_tasks),
        "retry_count": state.get("retry_count", 0),
    }

    logger.info(
        "node.finalize_run.start",
        run_id=run_id,
        status=terminal_status,
        task_count=metadata["task_count"],
    )

    # Update runs table using the shared engine
    engine = get_db_engine()
    if engine is not None:
        try:
            session_factory = async_sessionmaker(
                bind=engine,
                expire_on_commit=False,
                autoflush=False,
            )
            async with session_factory() as session:
                await session.execute(
                    text(
                        """
                        UPDATE runs
                        SET
                            status       = :status,
                            output       = :output,
                            error        = :error,
                            completed_at = NOW(),
                            metadata     = metadata || CAST(:meta AS jsonb)
                        WHERE id = :run_id
                        """
                    ),
                    {
                        "run_id": run_id,
                        "status": terminal_status,
                        "output": final_output,
                        "error": error,
                        "meta": json.dumps(metadata),
                    },
                )

                # Commit the runs table update. Event persistence is handled
                # centrally by sse_emitter.emit_event() to avoid duplication.
                await session.commit()

            logger.info("node.finalize_run.db_updated", run_id=run_id, status=terminal_status)

        except Exception as exc:
            logger.error("node.finalize_run.db_error", run_id=run_id, error=str(exc))

    # Publish Kafka event
    await _publish_run_event(
        run_id=run_id,
        terminal_status=terminal_status,
        final_output=final_output,
        error=error,
    )
    
    try:
        _redis_client = get_redis_client()
        if _redis_client is None:
            logger.error(
                "finalize_run.redis_client_none",
                run_id=run_id,
                warning="SSE terminal event will NOT be delivered — _redis_client is None",
            )
        else:
            event_type_sse = "run_complete" if terminal_status == "completed" else "run_error"
            await emit_event(
                run_id=run_id,
                event_type=event_type_sse,
                agent_name="orchestrator.finalize_run",
                payload={
                    "status": terminal_status,
                    "output": final_output[:500] if final_output else None,
                    "error": error,
                    **metadata,
                },
                redis_client=_redis_client,
            )
            logger.info(
                "finalize_run.sse_terminal_emitted",
                run_id=run_id,
                event_type=event_type_sse,
            )
    except Exception as _exc:
        logger.warning("finalize_run.emit_failed", run_id=run_id, error=str(_exc))

    logger.info("node.finalize_run.complete", run_id=run_id, status=terminal_status)
    return {"status": terminal_status}


async def _publish_run_event(
    run_id: str,
    terminal_status: str,
    final_output: str | None,
    error: str | None,
) -> None:
    """
    Publish run_complete or run_error event to nexus.events Kafka topic.

    Failures are logged and swallowed — Kafka publish must not abort finalization.

    Args:
        run_id: The orchestration run ID.
        terminal_status: "completed" or "failed".
        final_output: Synthesized answer (None on failure).
        error: Error message (None on success).
    """
    from config import settings
    from shared.kafka_client import KafkaProducerFactory

    event_type = "run_complete" if terminal_status == "completed" else "run_error"

    try:
        producer = await KafkaProducerFactory.get_producer(
            bootstrap_servers=settings.kafka_bootstrap_servers
        )
        event = EventMessage(
            run_id=run_id,
            event_type=event_type,
            source="orchestrator.finalize_run",
            payload={
                "status": terminal_status,
                "output": final_output[:500] if final_output else None,
                "error": error,
            },
        )
        await producer.send(
            settings.kafka_topic_events,
            value=event.model_dump_json().encode(),
        )
        logger.info("node.finalize_run.kafka_published", run_id=run_id, event_type=event_type)
    except Exception as exc:
        logger.warning("node.finalize_run.kafka_error", run_id=run_id, error=str(exc))