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

import httpx
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from dependencies import get_current_user, get_db_session

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
        query: The original user query (truncated to 200 chars in list view).
        created_at: ISO 8601 UTC timestamp string.
    """

    run_id: str
    status: str
    query: str
    created_at: str


class CreateRunResponse(BaseModel):
    """
    Response returned immediately after POST /api/v1/runs.

    The run is created synchronously but the orchestration executes
    asynchronously — status is always "running" on creation.

    Attributes:
        run_id: UUID of the newly created run.
        status: Always "running" for a freshly created run.
    """

    run_id: str
    status: str = "running"


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

    # Insert run row — status starts as "running" (orchestrator will update to
    # "completed" or "failed" via finalize_run node)
    result = await db.execute(
        text(
            """
            INSERT INTO runs (user_id, query, status)
            VALUES (:user_id, :query, 'running')
            RETURNING id::text, created_at
            """
        ),
        {"user_id": user_id, "query": body.query},
    )
    row = result.fetchone()
    await db.commit()

    run_id: str = row.id

    logger.info("runs.create", run_id=run_id, user_id=user_id, query=body.query[:80])

    # Dispatch to Orchestrator — fire-and-forget, do not await completion
    await _dispatch_to_orchestrator(
        run_id=run_id,
        query=body.query,
        user_id=user_id,
    )

    return CreateRunResponse(run_id=run_id, status="running")


async def _dispatch_to_orchestrator(
    run_id: str,
    query: str,
    user_id: str,
) -> None:
    """
    Fire POST /orchestrate to the Orchestrator service.

    Uses a short connect timeout (5s) so the Gateway returns quickly even
    if the Orchestrator is slow to accept the connection. Read timeout is
    intentionally short — we only need the Orchestrator to acknowledge the
    dispatch, not wait for it to complete.

    Failures are logged as ERROR but do not raise — the run row already
    exists in Postgres and the client can poll GET /api/v1/runs/{run_id}
    for status updates.

    Args:
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
            if response.status_code != 200:
                logger.error(
                    "runs.dispatch_failed",
                    run_id=run_id,
                    status=response.status_code,
                    body=response.text[:200],
                )
            else:
                logger.info("runs.dispatched", run_id=run_id)

    except httpx.ConnectError:
        logger.error(
            "runs.orchestrator_unreachable",
            run_id=run_id,
            orchestrator_url=settings.orchestrator_url,
        )
    except httpx.TimeoutException:
        logger.error("runs.orchestrator_timeout", run_id=run_id)
    except Exception as exc:
        logger.error("runs.dispatch_error", run_id=run_id, error=str(exc))


# ── GET /api/v1/runs ──────────────────────────────────────────────────────────


@router.get(
    "",
    response_model=list[RunSummary],
    summary="List all runs for the authenticated user",
)
async def list_runs(
    current_user: Annotated[dict[str, str], Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    status_filter: str | None = Query(default=None, alias="status"),
) -> list[RunSummary]:
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

    query_sql = """
        SELECT
            id::text        AS run_id,
            status,
            query,
            created_at::text AS created_at
        FROM runs
        WHERE user_id = :user_id
        {status_clause}
        ORDER BY created_at DESC
        LIMIT :limit OFFSET :offset
    """

    params: dict[str, Any] = {
        "user_id": user_id,
        "limit": limit,
        "offset": offset,
    }

    if status_filter:
        query_sql = query_sql.format(status_clause="AND status = :status")
        params["status"] = status_filter
    else:
        query_sql = query_sql.format(status_clause="")

    result = await db.execute(text(query_sql), params)
    rows = result.fetchall()

    logger.info("runs.list", user_id=user_id, count=len(rows))

    return [
        RunSummary(
            run_id=row.run_id,
            status=row.status,
            query=row.query[:200],
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
                id::text        AS run_id,
                status,
                query,
                created_at::text AS created_at
            FROM runs
            WHERE id = :run_id
              AND user_id = :user_id
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
    )