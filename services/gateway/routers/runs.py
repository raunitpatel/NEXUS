"""
Runs router for the API Gateway.

Endpoints:
  POST ""          — create a new run, insert into Postgres, dispatch to Orchestrator
  GET  ""          — list all runs for the authenticated user (paginated, newest first)
  GET  "/{run_id}" — get a single run by ID (ownership enforced)

All endpoints require a valid JWT (enforced by AuthMiddleware).
"""

from __future__ import annotations

from typing import Annotated, Any
import json
from datetime import datetime, timezone

import httpx
import structlog
from config import settings
from dependencies import get_current_user, get_db_session
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)
router = APIRouter()


# ── Request / response models ─────────────────────────────────────────────────


class CreateRunRequest(BaseModel):
    """
    Payload for POST /api/v1/runs.

    Attributes:
        query: The user's natural language query. Must be non-empty, ≤4096 chars.
    """

    query: str = Field(..., min_length=1, max_length=4096, strip_whitespace=True)


class RunSummary(BaseModel):
    """
    Run representation returned in list and create responses.

    Attributes:
        run_id: UUID of the run row.
        status: Current run lifecycle status.
        query: The original user query.
        created_at: ISO 8601 UTC timestamp string.
        duration_seconds: total time to run.
        agents_used: all agent called by orchestrator.
    """

    run_id: str
    status: str
    query: str
    created_at: str
    duration_seconds: int | None = None
    agents_used: list[str] = Field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    latency_ms: float | None = None


class RunListResponse(BaseModel):
    """
    Paginated run list response used by history views.
    """

    runs: list[RunSummary]
    total_count: int
    page: int
    size: int


class RunEventSummary(BaseModel):
    """
    Event representation returned for a run thought trace.

    Attributes:
        event_id: UUID of the persisted event row.
        run_id: UUID of the parent run.
        task_id: Optional task UUID associated with the event.
        event_type: Semantic event type stored in events.type.
        source: Dotted source identifier for the emitter.
        payload: JSON payload for the event body.
        created_at: ISO timestamp string for display ordering.
    """

    event_id: str
    run_id: str
    task_id: str | None = None
    event_type: str
    source: str
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: str


class CreateRunResponse(BaseModel):
    """
    Response returned immediately after POST /api/v1/runs.

    The run is created synchronously but the orchestration executes
    asynchronously — status is "pending" until the Orchestrator has
    accepted the dispatch.

    Attributes:
        run_id: UUID of the newly created run.
        status: Current status of the run after dispatch attempt.
    """

    run_id: str
    status: str = "pending"


class CancelRunResponse(BaseModel):
    """
    Response returned after POST /api/v1/runs/{run_id}/cancel.

    Attributes:
        run_id: UUID of the cancelled run.
        status: Always "cancelled" after successful cancellation.
    """

    run_id: str
    status: str = "cancelled"


# ── POST /api/v1/runs ─────────────────────────────────────────────────────────


@router.post(
    "",
    response_model=CreateRunResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new agent orchestration run",
)
async def create_run(
    body: CreateRunRequest,
    current_user: Annotated[dict[str, str], Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> CreateRunResponse:
    """
    Create a new run record and dispatch it to the Orchestrator.

    Inserts a runs row with status='running', then fires a non-blocking
    POST to the Orchestrator's /orchestrate endpoint. Returns run_id
    immediately — orchestration executes asynchronously.

    Args:
        body: CreateRunRequest with the user's query string.
        current_user: Injected by get_current_user — dict with user_id and jti.
        db: Injected async SQLAlchemy session.

    Returns:
        CreateRunResponse with run_id and status "running".

    Raises:
        HTTPException 503: If the Orchestrator is unreachable (run is still
            created in DB so the client can poll for status).
    """
    user_id = current_user["user_id"]

    # Insert run row — status starts as "pending" until Orchestrator accepts it.
    result = await db.execute(
        text(
            """
            INSERT INTO runs (user_id, query)
            VALUES (:user_id, :query)
            RETURNING id::text, created_at
            """
        ),
        {"user_id": user_id, "query": body.query},
    )
    row = result.fetchone()
    await db.commit()

    run_id: str = row.id

    logger.info("runs.create", run_id=run_id, user_id=user_id, query=body.query[:80])

    dispatch_status = await _dispatch_to_orchestrator(
        db=db,
        run_id=run_id,
        query=body.query,
        user_id=user_id,
    )

    return CreateRunResponse(run_id=run_id, status=dispatch_status or "pending")


async def _mark_run_failed(db: AsyncSession, run_id: str, error: str) -> None:
    await db.execute(
        text(
            """
            UPDATE runs
            SET status = 'failed', error = :error, completed_at = NOW(), metadata = metadata || CAST(:meta AS jsonb)
            WHERE id = :run_id
            """
        ),
        {
            "run_id": run_id,
            "error": error,
            "meta": json.dumps(
                {
                    "last_dispatch_error": error,
                    "dispatch_failed_at": datetime.now(timezone.utc).isoformat(),
                }
            ),
        },
    )
    await db.commit()


async def _dispatch_to_orchestrator(
    db: AsyncSession,
    run_id: str,
    query: str,
    user_id: str,
) -> str | None:
    """
    Fire POST /orchestrate to the Orchestrator service.

    Uses a short connect timeout (5s) so the Gateway returns quickly even
    if the Orchestrator is slow to accept the connection. Read timeout is
    intentionally short — we only need the Orchestrator to acknowledge the
    dispatch, not wait for it to complete.

    On success the run row remains pending until the Orchestrator updates
    it to running. On failure the row is marked failed so clients can observe
    the correct terminal state.

    Args:
        db: Active database session.
        run_id: UUID of the newly created run.
        query: The user's query string.
        user_id: UUID of the authenticated user.
    """
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(connect=5.0, read=10.0, write=5.0, pool=5.0)
        ) as client:
            response = await client.post(
                f"{settings.orchestrator_url}/orchestrate",
                json={
                    "run_id": run_id,
                    "query": query,
                    "user_id": user_id,
                },
            )

            if response.status_code == 200:
                logger.info("runs.dispatched", run_id=run_id)
                return "pending"

            if response.status_code == 409:
                logger.info(
                    "runs.dispatch_conflict",
                    run_id=run_id,
                    status=response.status_code,
                    body=response.text[:200],
                )
                return "cancelled"

            error = f"Orchestrator responded {response.status_code}: {response.text[:200]}"
            logger.error("runs.dispatch_failed", run_id=run_id, status=response.status_code, body=response.text[:200])
            await _mark_run_failed(db, run_id, error)
            return "failed"

    except httpx.ConnectError:
        error = "Orchestrator unreachable"
        logger.error(
            "runs.orchestrator_unreachable",
            run_id=run_id,
            orchestrator_url=settings.orchestrator_url,
        )
        await _mark_run_failed(db, run_id, error)
        return "failed"
    except httpx.TimeoutException:
        error = "Orchestrator dispatch timed out"
        logger.error("runs.orchestrator_timeout", run_id=run_id)
        await _mark_run_failed(db, run_id, error)
        return "failed"
    except Exception as exc:
        error = f"Dispatch failure: {exc}"
        logger.error("runs.dispatch_error", run_id=run_id, error=str(exc))
        await _mark_run_failed(db, run_id=run_id, error=error)
        return "failed"


# ── GET /api/v1/runs ──────────────────────────────────────────────────────────


@router.get(
    "",
    response_model=list[RunSummary] | RunListResponse,
    summary="List all runs for the authenticated user",
)
async def list_runs(
    current_user: Annotated[dict[str, str], Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    page: int | None = Query(default=None, ge=1),
    size: int | None = Query(default=None, ge=1, le=200),
    status_filter: str | None = Query(default=None, alias="status"),
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
) -> list[RunSummary] | RunListResponse:
    """
    Return all runs belonging to the authenticated user, newest first.

    Ownership is enforced by WHERE user_id = :user_id — users never see
    other users' runs regardless of what run_id they guess.

    Args:
        current_user: Injected by get_current_user.
        db: Injected async SQLAlchemy session.
        limit: Max runs to return (default 50, max 200).
        offset: Pagination offset.
        status_filter: Optional status filter (pending/running/completed/failed/cancelled).

    Returns:
        List of RunSummary objects ordered by created_at DESC.
    """
    user_id = current_user["user_id"]

    use_paginated_response = page is not None or size is not None
    resolved_size = size if size is not None else limit
    resolved_page = page if page is not None else (offset // resolved_size) + 1
    resolved_offset = (resolved_page - 1) * resolved_size if use_paginated_response else offset

    where_clauses = ["r.user_id = :user_id"]
    params: dict[str, Any] = {
        "user_id": user_id,
        "limit": resolved_size,
        "offset": resolved_offset,
    }

    if status_filter:
        where_clauses.append("r.status = :status")
        params["status"] = status_filter
    if start_date:
        where_clauses.append("r.created_at >= CAST(:start_date AS timestamptz)")
        params["start_date"] = start_date
    if end_date:
        where_clauses.append("r.created_at < CAST(:end_date AS date) + INTERVAL '1 day'")
        params["end_date"] = end_date

    where_sql = " AND ".join(where_clauses)

    query_sql = f"""
                SELECT
                    r.id::text AS run_id,
                    r.status,
                    r.query,
                    r.created_at::text AS created_at,

                    CASE
                        WHEN r.completed_at IS NOT NULL THEN
                            EXTRACT(EPOCH FROM (r.completed_at - r.created_at))::INT
                        ELSE NULL
                    END AS duration_seconds,

                    COALESCE((r.metadata->>'input_tokens')::INT, 0) AS input_tokens,
                    COALESCE((r.metadata->>'output_tokens')::INT, 0) AS output_tokens,
                    COALESCE((r.metadata->>'input_tokens')::INT, 0)
                      + COALESCE((r.metadata->>'output_tokens')::INT, 0) AS total_tokens,
                    CASE
                        WHEN r.metadata ? 'latency_ms' THEN (r.metadata->>'latency_ms')::FLOAT
                        WHEN r.completed_at IS NOT NULL THEN
                            EXTRACT(EPOCH FROM (r.completed_at - r.created_at)) * 1000
                        ELSE NULL
                    END AS latency_ms,

                    COALESCE(
                        ARRAY_AGG(DISTINCT a.name)
                        FILTER (WHERE a.name IS NOT NULL),
                        '{{}}'
                    ) AS agents_used

                FROM runs r
                LEFT JOIN tasks t
                    ON t.run_id = r.id
                LEFT JOIN agents a
                    ON a.id = t.agent_id

                WHERE {where_sql}

                GROUP BY r.id

                ORDER BY r.created_at DESC
                LIMIT :limit OFFSET :offset
            """

    result = await db.execute(text(query_sql), params)
    rows = result.fetchall()

    logger.info("runs.list", user_id=user_id, count=len(rows))

    run_summaries = [
        RunSummary(
            run_id=row.run_id,
            status=row.status,
            query=row.query[:200],
            created_at=row.created_at,
            duration_seconds=row.duration_seconds,
            agents_used=row.agents_used or [],
            input_tokens=row.input_tokens or 0,
            output_tokens=row.output_tokens or 0,
            total_tokens=row.total_tokens or 0,
            latency_ms=row.latency_ms,
        )
        for row in rows
    ]

    if not use_paginated_response:
        return run_summaries

    count_sql = f"""
        SELECT COUNT(*) AS total_count
        FROM runs r
        WHERE {where_sql}
    """
    count_result = await db.execute(text(count_sql), params)
    count_row = count_result.fetchone()

    return RunListResponse(
        runs=run_summaries,
        total_count=count_row.total_count or 0,
        page=resolved_page,
        size=resolved_size,
    )


# ── GET /api/v1/runs/{run_id}/events ──────────────────────────────────────────


@router.get(
    "/{run_id}/events",
    response_model=list[RunEventSummary],
    summary="List thought-trace events for a run",
)
async def list_run_events(
    run_id: str,
    current_user: Annotated[dict[str, str], Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    limit: int = Query(default=200, ge=1, le=500),
) -> list[RunEventSummary]:
    """
    Return persisted events for a single run, enforcing ownership.

    Events are persisted by the orchestrator SSE emitter. This endpoint lets
    completed and failed run detail pages render historical thought traces
    after the short-lived Redis SSE replay buffer has expired.
    """
    user_id = current_user["user_id"]

    result = await db.execute(
        text(
            """
            SELECT
                e.id::text AS event_id,
                e.run_id::text AS run_id,
                e.task_id::text AS task_id,
                e.type AS event_type,
                e.source,
                e.payload,
                e.created_at::text AS created_at
            FROM events e
            INNER JOIN runs r
                ON r.id = e.run_id
            WHERE e.run_id = :run_id
              AND r.user_id = :user_id
            ORDER BY e.created_at ASC
            LIMIT :limit
            """
        ),
        {"run_id": run_id, "user_id": user_id, "limit": limit},
    )
    rows = result.fetchall()

    # Keep the same "not found or not yours" behavior as GET /runs/{run_id}.
    if not rows:
        owner_check = await db.execute(
            text("SELECT 1 FROM runs WHERE id = :run_id AND user_id = :user_id"),
            {"run_id": run_id, "user_id": user_id},
        )
        if owner_check.fetchone() is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Run {run_id} not found",
            )

    logger.info("runs.events.list", run_id=run_id, user_id=user_id, count=len(rows))

    return [
        RunEventSummary(
            event_id=row.event_id,
            run_id=row.run_id,
            task_id=row.task_id,
            event_type=row.event_type,
            source=row.source,
            payload=row.payload or {},
            created_at=row.created_at,
        )
        for row in rows
    ]


# ── GET /api/v1/runs/{run_id} ─────────────────────────────────────────────────


@router.get(
    "/{run_id}",
    response_model=RunSummary,
    summary="Get a single run by ID",
)
async def get_run(
    run_id: str,
    current_user: Annotated[dict[str, str], Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> RunSummary:
    """
    Return a single run by ID, enforcing ownership.

    Returns 404 if the run does not exist or belongs to a different user.
    This prevents run ID enumeration attacks — a user cannot distinguish
    between "run does not exist" and "run exists but belongs to someone else".

    Args:
        run_id: UUID string of the run to fetch.
        current_user: Injected by get_current_user.
        db: Injected async SQLAlchemy session.

    Returns:
        RunSummary for the requested run.

    Raises:
        HTTPException 404: If run not found or owned by a different user.
    """
    user_id = current_user["user_id"]

    result = await db.execute(
        text(
            """
            SELECT
                r.id::text AS run_id,
                r.status,
                r.query,
                r.created_at::text AS created_at,

                CASE
                    WHEN r.completed_at IS NOT NULL THEN
                        EXTRACT(EPOCH FROM (r.completed_at - r.created_at))::INT
                    ELSE NULL
                END AS duration_seconds,

                COALESCE((r.metadata->>'input_tokens')::INT, 0) AS input_tokens,
                COALESCE((r.metadata->>'output_tokens')::INT, 0) AS output_tokens,
                COALESCE((r.metadata->>'input_tokens')::INT, 0)
                  + COALESCE((r.metadata->>'output_tokens')::INT, 0) AS total_tokens,
                CASE
                    WHEN r.metadata ? 'latency_ms' THEN (r.metadata->>'latency_ms')::FLOAT
                    WHEN r.completed_at IS NOT NULL THEN
                        EXTRACT(EPOCH FROM (r.completed_at - r.created_at)) * 1000
                    ELSE NULL
                END AS latency_ms,

                COALESCE(
                    ARRAY_AGG(DISTINCT a.name)
                    FILTER (WHERE a.name IS NOT NULL),
                    '{}'
                ) AS agents_used

            FROM runs r

            LEFT JOIN tasks t
                ON t.run_id = r.id

            LEFT JOIN agents a
                ON a.id = t.agent_id

            WHERE r.id = :run_id
              AND r.user_id = :user_id

            GROUP BY r.id
            """
        ),
        {"run_id": run_id, "user_id": user_id},
    )

    row = result.fetchone()

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run {run_id} not found",
        )

    logger.info("runs.get", run_id=run_id, user_id=user_id)

    return RunSummary(
        run_id=row.run_id,
        status=row.status,
        query=row.query,
        created_at=row.created_at,
        duration_seconds=row.duration_seconds,
        agents_used=row.agents_used or [],
        input_tokens=row.input_tokens or 0,
        output_tokens=row.output_tokens or 0,
        total_tokens=row.total_tokens or 0,
        latency_ms=row.latency_ms,
    )


@router.post(
    "/{run_id}/cancel",
    response_model=CancelRunResponse,
    summary="Cancel a pending or running run",
)
async def cancel_run(
    run_id: str,
    current_user: Annotated[dict[str, str], Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> CancelRunResponse:
    user_id = current_user["user_id"]

    result = await db.execute(
        text(
            """
            UPDATE runs
            SET
                status = 'cancelled',
                completed_at = NOW(),
                metadata = metadata || CAST(:meta AS jsonb)
            WHERE id = :run_id
              AND user_id = :user_id
              AND status IN ('pending', 'running')
            RETURNING id::text
            """
        ),
        {
            "run_id": run_id,
            "user_id": user_id,
            "meta": json.dumps(
                {
                    "cancelled_at": datetime.now(timezone.utc).isoformat(),
                }
            ),
        },
    )
    row = result.fetchone()
    if row is None:
        owner_check = await db.execute(
            text(
                "SELECT 1 FROM runs WHERE id = :run_id AND user_id = :user_id"
            ),
            {"run_id": run_id, "user_id": user_id},
        )
        if owner_check.fetchone() is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Run {run_id} not found",
            )

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Run {run_id} cannot be cancelled",
        )

    await db.execute(
        text(
            """
            UPDATE tasks
            SET
                status       = 'failed',
                error        = COALESCE(NULLIF(error, ''), 'Run was cancelled before this task completed'),
                completed_at = COALESCE(completed_at, NOW())
            WHERE run_id = :run_id
              AND status IN ('pending', 'running', 'retrying')
            """
        ),
        {"run_id": run_id},
    )
    await db.commit()
    logger.info("runs.cancelled", run_id=run_id, user_id=user_id)
    return CancelRunResponse(run_id=run_id)
