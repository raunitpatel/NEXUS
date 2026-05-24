"""
Metrics router for the API Gateway.

Returns per-user aggregated statistics derived from Postgres — not raw
Prometheus metrics (those are at GET /metrics for Prometheus scraping).
All data is scoped to the authenticated user via WHERE user_id = :user_id.

Endpoints:
  GET "/summary"        — overall token usage, run counts, success rate
  GET "/agent-stats"    — per-agent breakdown of runs, latency, success rate
  GET "/token-usage"    — daily token usage for the past N days (for charts)
  GET "/latency"        — per-agent average latency for the past N days
"""

from __future__ import annotations

from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies import get_current_user, get_db_session

logger = structlog.get_logger(__name__)
router = APIRouter()


# ── Response models ───────────────────────────────────────────────────────────


class MetricsSummary(BaseModel):
    """
    High-level metrics summary for the authenticated user.

    Attributes:
        total_runs: All-time run count for this user.
        successful_runs: Runs with status "completed".
        failed_runs: Runs with status "failed".
        success_rate: successful_runs / total_runs as 0.0–1.0 float.
        total_input_tokens: Sum of metadata.input_tokens across all runs.
        total_output_tokens: Sum of metadata.output_tokens across all runs.
        avg_run_duration_ms: Average latency_ms from run metadata.
        active_runs: Runs currently in status "running".
        period_days: The lookback window used for token/latency stats.
    """

    total_runs: int
    successful_runs: int
    failed_runs: int
    success_rate: float
    total_input_tokens: int
    total_output_tokens: int
    avg_run_duration_ms: float
    active_runs: int
    period_days: int


class AgentStat(BaseModel):
    """
    Per-agent statistics for the authenticated user.

    Attributes:
        agent_type: Agent type slug (search/code/memory/tool).
        total_tasks: Total tasks dispatched to this agent type.
        successful_tasks: Tasks with status "completed".
        failed_tasks: Tasks with status "failed".
        success_rate: successful_tasks / total_tasks as 0.0–1.0.
        avg_duration_ms: Average task duration from tasks table.
    """

    agent_type: str
    total_tasks: int
    successful_tasks: int
    failed_tasks: int
    success_rate: float
    avg_duration_ms: float


class DailyTokenUsage(BaseModel):
    """
    Token usage for a single day — used to power the TokenUsageChart.

    Attributes:
        date: ISO date string (YYYY-MM-DD).
        input_tokens: Total LLM input tokens consumed on this date.
        output_tokens: Total LLM output tokens consumed on this date.
        run_count: Number of runs completed on this date.
    """

    date: str
    input_tokens: int
    output_tokens: int
    run_count: int


class DailyLatency(BaseModel):
    """
    Average run latency for a single day — used to power the LatencyChart.

    Attributes:
        date: ISO date string (YYYY-MM-DD).
        avg_duration_ms: Average wall-clock duration across all completed runs.
        p95_duration_ms: 95th percentile duration (approximated via PERCENTILE_CONT).
        run_count: Number of completed runs on this date.
    """

    date: str
    avg_duration_ms: float
    p95_duration_ms: float
    run_count: int


# ── GET /api/v1/metrics/summary ───────────────────────────────────────────────


@router.get(
    "/summary",
    response_model=MetricsSummary,
    summary="Overall metrics summary for the authenticated user",
)
async def get_summary(
    current_user: Annotated[dict[str, str], Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    days: int = Query(default=7, ge=1, le=90, description="Lookback window in days"),
) -> MetricsSummary:
    """
    Return aggregated run statistics for the authenticated user.

    Token and latency stats use the `days` lookback window. Run counts
    are all-time so the user always sees their complete history summary.

    Args:
        current_user: Injected by get_current_user.
        db: Injected async SQLAlchemy session.
        days: Lookback window for token and latency aggregations.

    Returns:
        MetricsSummary with counts, rates, and token totals.
    """
    user_id = current_user["user_id"]

    # All-time run counts and active runs
    counts_result = await db.execute(
        text(
            """
            SELECT
                COUNT(*)                                            AS total_runs,
                COUNT(*) FILTER (WHERE status = 'completed')       AS successful_runs,
                COUNT(*) FILTER (WHERE status = 'failed')          AS failed_runs,
                COUNT(*) FILTER (WHERE status = 'running')         AS active_runs
            FROM runs
            WHERE user_id = :user_id
            """
        ),
        {"user_id": user_id},
    )
    counts = counts_result.fetchone()

    total_runs: int = counts.total_runs or 0
    successful_runs: int = counts.successful_runs or 0
    failed_runs: int = counts.failed_runs or 0
    active_runs: int = counts.active_runs or 0
    success_rate: float = successful_runs / total_runs if total_runs > 0 else 0.0

    # Token usage and latency for the lookback window
    # Tokens are stored as metadata JSONB keys by finalize_run node
    tokens_result = await db.execute(
        text(
            """
            SELECT
                COALESCE(SUM((metadata->>'input_tokens')::bigint), 0)   AS total_input_tokens,
                COALESCE(SUM((metadata->>'output_tokens')::bigint), 0)  AS total_output_tokens,
                COALESCE(AVG((metadata->>'duration_ms')::float), 0)      AS avg_run_duration_ms
            FROM runs
            WHERE user_id = :user_id
              AND status = 'completed'
              AND created_at >= NOW() - INTERVAL '1 day' * :days
            """
        ),
        {"user_id": user_id, "days": days},
    )
    tokens = tokens_result.fetchone()

    logger.info("metrics.summary", user_id=user_id, days=days, total_runs=total_runs)

    return MetricsSummary(
        total_runs=total_runs,
        successful_runs=successful_runs,
        failed_runs=failed_runs,
        success_rate=round(success_rate, 4),
        total_input_tokens=int(tokens.total_input_tokens or 0),
        total_output_tokens=int(tokens.total_output_tokens or 0),
        avg_run_duration_ms=round(float(tokens.avg_run_duration_ms or 0), 1),
        active_runs=active_runs,
        period_days=days,
    )


# ── GET /api/v1/metrics/agent-stats ──────────────────────────────────────────


@router.get(
    "/agent-stats",
    response_model=list[AgentStat],
    summary="Per-agent task statistics for the authenticated user",
)
async def get_agent_stats(
    current_user: Annotated[dict[str, str], Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    days: int = Query(default=7, ge=1, le=90),
) -> list[AgentStat]:
    """
    Return per-agent-type task counts, success rates, and average latency.

    Joins tasks → runs to enforce user ownership — only tasks from the
    authenticated user's runs are included. Uses the tasks table type column
    which maps directly to agent type (search/code/memory_read/memory_write/tool).

    Args:
        current_user: Injected by get_current_user.
        db: Injected async SQLAlchemy session.
        days: Lookback window in days.

    Returns:
        List of AgentStat objects, one per agent type that has tasks.
    """
    user_id = current_user["user_id"]

    result = await db.execute(
        text(
            """
            SELECT
                t.type                                                      AS agent_type,
                COUNT(*)                                                    AS total_tasks,
                COUNT(*) FILTER (WHERE t.status = 'completed')             AS successful_tasks,
                COUNT(*) FILTER (WHERE t.status = 'failed')                AS failed_tasks,
                COALESCE(
                    AVG(
                        EXTRACT(EPOCH FROM (t.completed_at - t.created_at)) * 1000
                    ) FILTER (WHERE t.completed_at IS NOT NULL),
                    0
                )                                                           AS avg_duration_ms
            FROM tasks t
            JOIN runs r ON r.id = t.run_id
            WHERE r.user_id = :user_id
              AND t.created_at >= NOW() - INTERVAL '1 day' * :days
            GROUP BY t.type
            ORDER BY total_tasks DESC
            """
        ),
        {"user_id": user_id, "days": days},
    )
    rows = result.fetchall()

    logger.info("metrics.agent_stats", user_id=user_id, days=days, agent_count=len(rows))

    return [
        AgentStat(
            agent_type=row.agent_type,
            total_tasks=row.total_tasks,
            successful_tasks=row.successful_tasks,
            failed_tasks=row.failed_tasks,
            success_rate=round(
                row.successful_tasks / row.total_tasks if row.total_tasks > 0 else 0.0,
                4,
            ),
            avg_duration_ms=round(float(row.avg_duration_ms or 0), 1),
        )
        for row in rows
    ]


# ── GET /api/v1/metrics/token-usage ──────────────────────────────────────────


@router.get(
    "/token-usage",
    response_model=list[DailyTokenUsage],
    summary="Daily token usage for the authenticated user (for charts)",
)
async def get_token_usage(
    current_user: Annotated[dict[str, str], Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    days: int = Query(default=7, ge=1, le=90),
) -> list[DailyTokenUsage]:
    """
    Return daily token usage totals for the past N days.

    Produces one row per calendar day ordered oldest-first so the frontend
    TokenUsageChart can render a time-series without sorting.
    Days with no completed runs are omitted (not zero-filled) — the frontend
    handles sparse data.

    Args:
        current_user: Injected by get_current_user.
        db: Injected async SQLAlchemy session.
        days: Number of calendar days to include.

    Returns:
        List of DailyTokenUsage ordered by date ASC.
    """
    user_id = current_user["user_id"]

    result = await db.execute(
        text(
            """
            SELECT
                DATE(created_at AT TIME ZONE 'UTC')                         AS date,
                COALESCE(SUM((metadata->>'input_tokens')::bigint), 0)       AS input_tokens,
                COALESCE(SUM((metadata->>'output_tokens')::bigint), 0)      AS output_tokens,
                COUNT(*)                                                     AS run_count
            FROM runs
            WHERE user_id = :user_id
              AND status = 'completed'
              AND created_at >= NOW() - INTERVAL '1 day' * :days
            GROUP BY DATE(created_at AT TIME ZONE 'UTC')
            ORDER BY date ASC
            """
        ),
        {"user_id": user_id, "days": days},
    )
    rows = result.fetchall()

    logger.info("metrics.token_usage", user_id=user_id, days=days, row_count=len(rows))

    return [
        DailyTokenUsage(
            date=str(row.date),
            input_tokens=int(row.input_tokens or 0),
            output_tokens=int(row.output_tokens or 0),
            run_count=int(row.run_count),
        )
        for row in rows
    ]


# ── GET /api/v1/metrics/latency ───────────────────────────────────────────────


@router.get(
    "/latency",
    response_model=list[DailyLatency],
    summary="Daily average run latency for the authenticated user (for charts)",
)
async def get_latency(
    current_user: Annotated[dict[str, str], Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    days: int = Query(default=7, ge=1, le=90),
) -> list[DailyLatency]:
    """
    Return daily average and p95 run latency for the past N days.

    Latency is computed from the latency_ms key stored in run metadata
    by finalize_run. Uses Postgres PERCENTILE_CONT for true p95.
    Days with no completed runs are omitted.

    Args:
        current_user: Injected by get_current_user.
        db: Injected async SQLAlchemy session.
        days: Number of calendar days to include.

    Returns:
        List of DailyLatency ordered by date ASC.
    """
    user_id = current_user["user_id"]

    result = await db.execute(
        text(
            """
            SELECT
                DATE(created_at AT TIME ZONE 'UTC')                             AS date,
                COALESCE(AVG((metadata->>'duration_ms')::float), 0)              AS avg_duration_ms,
                COALESCE(
                    PERCENTILE_CONT(0.95) WITHIN GROUP (
                        ORDER BY (metadata->>'duration_ms')::float
                    ),
                    0
                )                                                               AS p95_duration_ms,
                COUNT(*)                                                         AS run_count
            FROM runs
            WHERE user_id = :user_id
              AND status = 'completed'
              AND metadata ? 'duration_ms'
              AND created_at >= NOW() - INTERVAL '1 day' * :days
            GROUP BY DATE(created_at AT TIME ZONE 'UTC')
            ORDER BY date ASC
            """
        ),
        {"user_id": user_id, "days": days},
    )
    rows = result.fetchall()

    logger.info("metrics.latency", user_id=user_id, days=days, row_count=len(rows))

    return [
        DailyLatency(
            date=str(row.date),
            avg_duration_ms=round(float(row.avg_duration_ms or 0), 1),
            p95_duration_ms=round(float(row.p95_duration_ms or 0), 1),
            run_count=int(row.run_count),
        )
        for row in rows
    ]