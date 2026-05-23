"""
Shared task persistence helpers for orchestrator nodes.

This module centralizes task table writes and existence checks so that the
orchestrator can persist every generated task before dispatching it.
"""

from __future__ import annotations

import json

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from state import TaskPlan
from nodes.db import get_db_engine

logger = structlog.get_logger(__name__)


# Maps orchestrator task types → agents table names
TASK_TYPE_TO_AGENT_NAME = {
    "search": "Search Agent",
    "code": "Code Agent",
    "memory_read": "Memory Agent",
    "memory_write": "Memory Agent",
    "tool": "Tool Agent",
}


async def insert_task_plan(run_id: str, task_plan: list[TaskPlan]) -> None:
    """Persist the full task plan into the tasks table before dispatch."""

    engine = get_db_engine()

    if engine is None:
        raise RuntimeError("DB engine not configured for task persistence")

    logger.info(
        "task.persist.start",
        run_id=run_id,
        task_count=len(task_plan),
    )

    session_factory = async_sessionmaker(
        bind=engine,
        expire_on_commit=False,
        autoflush=False,
    )

    async with session_factory() as session:
        inserted = 0

        for task in task_plan:
            try:
                task_type = task["task_type"]

                # Resolve agent name from task type
                agent_name = TASK_TYPE_TO_AGENT_NAME.get(task_type)

                logger.info(
                    "task.persist.agent_lookup",
                    run_id=run_id,
                    task_id=task["task_id"],
                    task_type=task_type,
                    resolved_agent_name=agent_name,
                )

                # Resolve agent_id from agents table
                agent_result = await session.execute(
                    text(
                        """
                        SELECT id
                        FROM agents
                        WHERE name = :agent_name
                        LIMIT 1
                        """
                    ),
                    {
                        "agent_name": agent_name,
                    },
                )

                agent_id = agent_result.scalar_one_or_none()

                if agent_id is None:
                    logger.warning(
                        "task.persist.agent_not_found",
                        run_id=run_id,
                        task_id=task["task_id"],
                        task_type=task_type,
                        agent_name=agent_name,
                    )

                # Persist task
                await session.execute(
                    text(
                        """
                        INSERT INTO tasks (
                            id,
                            run_id,
                            agent_id,
                            type,
                            input
                        )
                        VALUES (
                            :id,
                            :run_id,
                            :agent_id,
                            :type,
                            CAST(:input AS jsonb)
                        )
                        """
                    ),
                    {
                        "id": task["task_id"],
                        "run_id": run_id,
                        "agent_id": agent_id,
                        "type": task_type,
                        "input": json.dumps(task["input"]),
                    },
                )

                inserted += 1

                logger.info(
                    "task.persist.row",
                    run_id=run_id,
                    task_id=task["task_id"],
                    task_type=task_type,
                    agent_id=str(agent_id) if agent_id else None,
                    agent_name=agent_name,
                )

            except Exception as exc:
                logger.error(
                    "task.persist.failed",
                    run_id=run_id,
                    task_id=task.get("task_id"),
                    error=str(exc),
                )
                raise

        await session.commit()

    if inserted != len(task_plan):
        logger.warning(
            "task.persist.mismatch",
            run_id=run_id,
            expected=len(task_plan),
            inserted=inserted,
        )

    logger.info(
        "task.persist.success",
        run_id=run_id,
        task_count=inserted,
    )


async def task_exists(task_id: str) -> bool:
    """Return True if the supplied task_id already exists in the tasks table."""

    engine = get_db_engine()

    if engine is None:
        raise RuntimeError("DB engine not configured for task persistence")

    session_factory = async_sessionmaker(
        bind=engine,
        expire_on_commit=False,
        autoflush=False,
    )

    async with session_factory() as session:
        result = await session.execute(
            text(
                """
                SELECT 1
                FROM tasks
                WHERE id = :task_id
                """
            ),
            {"task_id": task_id},
        )

        return result.scalar_one_or_none() is not None