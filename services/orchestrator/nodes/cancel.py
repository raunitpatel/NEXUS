"""
Cancellation helpers for orchestrator nodes.

These helpers query the shared runs table to detect when a user has
requested cancellation for the active run. Nodes can call maybe_cancel_run()
before performing expensive work and let the LangGraph router transition the
run to finalize_run early.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from nodes.db import get_db_engine


async def is_run_cancelled(run_id: str) -> bool:
    """Return True when the run row has status cancelled."""
    engine = get_db_engine()
    if engine is None:
        return False

    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
    async with session_factory() as session:
        result = await session.execute(
            text("SELECT status FROM runs WHERE id = :run_id"),
            {"run_id": run_id},
        )
        row = result.fetchone()

    return bool(row and row.status == "cancelled")


async def maybe_cancel_run(run_id: str) -> dict[str, Any]:
    """Return cancellation state when the run has been cancelled."""
    if await is_run_cancelled(run_id):
        return {
            "cancelled": True,
            "status": "cancelled",
            "error": "Cancelled by user",
        }
    return {}
