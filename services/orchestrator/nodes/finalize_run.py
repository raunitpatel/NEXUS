"""
finalize_run node — writes terminal state to Postgres and emits run_complete event.

Executes:
  - UPDATE runs SET status, output, error, completed_at, metadata WHERE id
  - INSERT INTO events (run_id, type, payload, source)
  - KafkaProducer.send(nexus.events, run_complete/run_error EventMessage)

Metadata accumulation strategy:
  The runs.metadata JSONB column is the single source of truth for
  post-run analytics. This node merges the following fields into it:

    input_tokens          — total LLM input tokens across all nodes
    output_tokens         — total LLM output tokens across all nodes
    task_count            — number of planned tasks
    completed_task_count  — tasks that reached terminal state
    retry_count           — total handle_error invocations
    task_summaries        — per-task agent_type + status + duration_ms + output_preview
    agent_types_used      — deduplicated list of agent types that ran
    total_duration_ms     — wall-clock ms from run creation to finalization (approx)
    finalized_at          — ISO UTC timestamp of finalization
    error_detail          — last error message, if any

  Existing keys in runs.metadata are preserved via JSON merge (||), so
  seed-data latency_ms values remain intact.

DB engine is accessed via nodes.db.get_db_engine().
"""

from __future__ import annotations

import json
import time
import logging
from datetime import datetime, timezone
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

# Standard Python logger for pre/post-write verification logging
_raw_logger = logging.getLogger(__name__)

def _extract_preview(data: Any) -> str | None:
    if isinstance(data, str):
        cleaned = data.strip()
        return cleaned if cleaned else None

    if isinstance(data, dict):
        for v in data.values():
            result = _extract_preview(v)
            if result:
                return result

    if isinstance(data, list):
        for item in data:
            result = _extract_preview(item)
            if result:
                return result

    return None

def _build_metadata(state: OrchestratorState, terminal_status: str) -> dict[str, Any]:
    """
    Build the full metadata dict to merge into runs.metadata.

    Collects all orchestration state fields that are useful for post-run
    analytics, history display, and debugging.

    Args:
        state: Final OrchestratorState after graph execution.
        terminal_status: "completed" or "failed".

    Returns:
        Dict of JSONB-safe values to merge into runs.metadata.
    """
    completed_tasks = state.get("completed_tasks", [])
    task_plan = state.get("task_plan", [])

    # Build per-task summaries — compact representation for the history page
    task_summaries: list[dict[str, Any]] = []
    for t in completed_tasks:
        output = t.get("output") or {}
        raw_response = t.get("raw_response") or {}

        output_preview = (
            _extract_preview(output)
            or _extract_preview(raw_response)
        )

        has_payload = bool(output or raw_response)

        task_summaries.append({
            "task_id": t.get("task_id"),
            "agent_type": t.get("agent_type"),
            "status": "failed" if t.get("error") else "completed",
            "duration_ms": t.get("duration_ms", 0),
            "attempt": t.get("attempt", 1),
            "output_preview": output_preview,
            "summary": t.get("summary"),
            "has_payload": has_payload,
            "error": t.get("error"),
        })

    # Deduplicated agent types in execution order
    seen: set[str] = set()
    agent_types_used: list[str] = []
    for t in completed_tasks:
        at = t.get("agent_type")
        if at and at not in seen:
            seen.add(at)
            agent_types_used.append(at)

    return {
        "input_tokens": state.get("input_tokens", 0),
        "output_tokens": state.get("output_tokens", 0),
        "task_count": len(task_plan),
        "completed_task_count": len(completed_tasks),
        "retry_count": state.get("retry_count", 0),
        "task_summaries": task_summaries,
        "agent_types_used": agent_types_used,
        "terminal_status": terminal_status,
        "error_detail": state.get("error"),
        "finalized_at": datetime.now(timezone.utc).isoformat(),
    }


async def finalize_run(state: OrchestratorState) -> dict[str, Any]:
    """
    Update runs table to terminal status and emit SSE run_complete/run_error event.

    Reads final_output and error from state. Builds a comprehensive metadata
    dict including task summaries, agent types used, and token counts. Merges
    this into runs.metadata using Postgres JSON merge operator (||) so existing
    seed-data fields (latency_ms, etc.) are preserved.

    Args:
        state: Current OrchestratorState after synthesize_output or handle_error.

    Returns:
        Partial state dict with status set to "completed" or "failed".
    """
    run_id = state["run_id"]
    final_output: str | None = state.get("final_output")
    error: str | None = state.get("error")

    terminal_status = "failed" if error else "completed"

    metadata = _build_metadata(state, terminal_status)

    # --- Pre-write logging ---
    _raw_logger.info(
        "[finalize_run] PRE-WRITE run_id=%s status=%s "
        "metadata_keys=%s task_summaries_count=%d agent_types=%s "
        "input_tokens=%d output_tokens=%d",
        run_id,
        terminal_status,
        list(metadata.keys()),
        len(metadata.get("task_summaries", [])),
        metadata.get("agent_types_used"),
        metadata.get("input_tokens", 0),
        metadata.get("output_tokens", 0),
    )

    logger.info(
        "node.finalize_run.start",
        run_id=run_id,
        status=terminal_status,
        task_count=metadata["task_count"],
        completed_task_count=metadata["completed_task_count"],
        agent_types_used=metadata["agent_types_used"],
    )

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
                await session.commit()

            # --- Post-write verification ---
            async with session_factory() as verify_session:
                row = await verify_session.execute(
                    text(
                        "SELECT status, metadata FROM runs WHERE id = :run_id"
                    ),
                    {"run_id": run_id},
                )
                result = row.fetchone()

            if result:
                persisted_meta = result.metadata or {}
                persisted_keys = list(persisted_meta.keys()) if isinstance(persisted_meta, dict) else []
                _raw_logger.info(
                    "[finalize_run] POST-WRITE VERIFIED run_id=%s "
                    "db_status=%s persisted_metadata_keys=%s "
                    "task_summaries_count=%d agent_types=%s",
                    run_id,
                    result.status,
                    persisted_keys,
                    len(persisted_meta.get("task_summaries", [])),
                    persisted_meta.get("agent_types_used"),
                )
            else:
                _raw_logger.error(
                    "[finalize_run] POST-WRITE VERIFICATION FAILED — "
                    "run_id=%s not found in DB after commit",
                    run_id,
                )

            logger.info(
                "node.finalize_run.db_updated",
                run_id=run_id,
                status=terminal_status,
                metadata_keys=list(metadata.keys()),
            )

        except Exception as exc:
            _raw_logger.error(
                "[finalize_run] DB WRITE FAILED run_id=%s error=%s",
                run_id,
                exc,
                exc_info=True,
            )
            logger.error("node.finalize_run.db_error", run_id=run_id, error=str(exc))
    else:
        logger.warning(
            "node.finalize_run.no_db_engine",
            run_id=run_id,
            note="DB engine not configured — metadata will NOT be persisted",
        )

    # Publish Kafka event
    await _publish_run_event(
        run_id=run_id,
        terminal_status=terminal_status,
        final_output=final_output,
        error=error,
        completed_tasks=state.get("completed_tasks", []),
    )

    # Emit SSE terminal event
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
                    "output": final_output if final_output else None,
                    "error": error,
                    "completed_tasks": state.get("completed_tasks", []),
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
    completed_tasks: list[dict],
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
                "output": final_output if final_output else None,
                "error": error,
                "completed_tasks": completed_tasks,
            },
        )
        await producer.send(
            settings.kafka_topic_events,
            value=event.model_dump_json().encode(),
        )
        logger.info("node.finalize_run.kafka_published", run_id=run_id, event_type=event_type)
    except Exception as exc:
        logger.warning("node.finalize_run.kafka_error", run_id=run_id, error=str(exc))