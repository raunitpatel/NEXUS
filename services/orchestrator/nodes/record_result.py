"""
record_result node — persists the completed TaskResult to Postgres and updates state.

Appends task_result to completed_tasks, clears pending_task, and executes an
async SQLAlchemy UPDATE on the tasks table. DB engine is accessed via the
module-level _db_engine reference set by main.py lifespan.

AGNT-010 adds tool_results table INSERT alongside the tasks UPDATE.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from state import OrchestratorState

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, AsyncSession

logger = structlog.get_logger(__name__)

# Module-level engine reference — set by main.py lifespan
# This is the standard pattern for sharing engine with LangGraph nodes
# that cannot receive FastAPI Depends() injection.
_db_engine: AsyncEngine | None = None


def set_db_engine(engine: AsyncEngine) -> None:
    """
    Store the AsyncEngine for use by record_result and finalize_run.

    Called once from main.py lifespan after engine creation.

    Args:
        engine: The SQLAlchemy async engine bound to nexus_db.
    """
    global _db_engine
    _db_engine = engine


async def _update_task_record(
    engine: AsyncEngine,
    task_id: str,
    status: str,
    output: dict[str, Any] | None,
    error: str | None,
    duration_ms: int,
) -> None:
    """
    Execute UPDATE tasks SET status, output, error, completed_at WHERE id.

    Args:
        engine: Async SQLAlchemy engine.
        task_id: UUID string of the task row.
        status: Terminal status — "completed" or "failed".
        output: JSONB output dict (None on failure).
        error: Error message string (None on success).
        duration_ms: Task wall-clock time in milliseconds.
    """
    session_factory = async_sessionmaker(
        bind=engine,
        expire_on_commit=False,
        autoflush=False,
    )
    async with session_factory() as session:
        await session.execute(
            text(
                """
                UPDATE tasks
                SET
                    status       = :status,
                    output       = CAST(:output AS jsonb),
                    error        = :error,
                    completed_at = NOW()
                WHERE id = :task_id
                """
            ),
            {
                "task_id": task_id,
                "status": status,
                "output": json.dumps(output) if output is not None else json.dumps({}),
                "error": error,
            },
        )
        await session.commit()


async def record_result(state: OrchestratorState) -> dict[str, Any]:
    """
    Append task_result to completed_tasks and persist to the tasks table.

    Clears pending_task and task_result after recording. DB write failure
    is logged as ERROR but does not abort the run — state is still updated.

    Args:
        state: Current OrchestratorState with task_result populated.

    Returns:
        Partial state dict with completed_tasks updated, pending_task cleared.
    """

    run_id = state["run_id"]
    task_result = state.get("task_result")

    if not task_result:
        logger.error("node.record_result.no_task_result", run_id=run_id)
        return {"error": "record_result called but task_result is None."}

    task_id = task_result["task_id"]
    has_error = bool(task_result.get("error"))
    db_status = "failed" if has_error else "completed"

    # Update DB
    if _db_engine is not None:
        try:
            await _update_task_record(
                engine=_db_engine,
                task_id=task_id,
                status=db_status,
                output=task_result.get("output"),
                error=task_result.get("error"),
                duration_ms=task_result.get("duration_ms", 0),
            )
            logger.info(
                "node.record_result.db_updated",
                run_id=run_id,
                task_id=task_id,
                status=db_status,
            )
        except Exception as exc:
            logger.error(
                "node.record_result.db_error",
                run_id=run_id,
                task_id=task_id,
                error=str(exc),
            )
    else:
        logger.warning("node.record_result.no_db_engine", run_id=run_id)

    completed_tasks = list(state.get("completed_tasks", []))
    completed_tasks.append(task_result)

    logger.info(
        "node.record_result.appended",
        run_id=run_id,
        task_id=task_id,
        completed_count=len(completed_tasks),
        total_count=len(state.get("task_plan", [])),
    )

    return {
        "completed_tasks": completed_tasks,
        "pending_task": None,
        "task_result": None,
    }