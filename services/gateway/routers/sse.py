"""
SSE proxy router for the API Gateway.

Proxies the Orchestrator's per-run SSE stream to the browser client.
Authentication uses ?token= query parameter because the browser EventSource
API does not support custom request headers.

Endpoint:
  GET /api/v1/sse/{run_id}?token=<jwt>

Authorization flow:
  1. Decode and validate JWT from ?token= query parameter
  2. Verify Redis session exists (revocation check)
  3. Confirm run ownership: runs.user_id == JWT sub claim
  4. Open httpx stream to http://nexus-orchestrator:8001/runs/{run_id}/stream
  5. Forward each SSE chunk to the browser
  6. Close stream on run_complete or run_error event type
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

import httpx
import redis.asyncio as aioredis
import structlog
from config import settings
from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from jose import JWTError, jwt
from shared.metrics import sse_connections_active, sse_events_emitted_total
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

logger = structlog.get_logger(__name__)
router = APIRouter()

# SSE events that signal the run has reached a terminal state.
# The proxy closes the stream within one iteration of receiving these.
_TERMINAL_EVENT_TYPES: frozenset[str] = frozenset({"run_complete", "run_error"})


async def _validate_token(token: str, redis_client: aioredis.Redis) -> str:
    """
    Validate a JWT token from the ?token= query parameter.

    Decodes the JWT signature and expiry, then verifies the session
    still exists in Redis (enables server-side revocation).

    Args:
        token: Raw JWT string from the ?token= query parameter.
        redis_client: Async Redis client from app.state.redis.

    Returns:
        user_id (JWT sub claim) on success.

    Raises:
        HTTPException 401: On invalid token, expired token, or missing session.
    """
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    user_id: str | None = payload.get("sub")
    jti: str | None = payload.get("jti")

    if not user_id or not jti:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token claims",
        )

    try:
        session_exists = await redis_client.exists(f"session:{jti}")
    except Exception as exc:
        logger.error("sse.redis_check_failed", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service unavailable",
        )

    if not session_exists:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired or revoked",
        )

    return user_id


async def _verify_run_ownership(
    run_id: str,
    user_id: str,
    request: Request,
) -> None:
    """
    Verify the authenticated user owns the requested run.

    Queries the runs table for the run's owner. Raises 404 if the run
    does not exist, 403 if the owner does not match the JWT sub.

    Args:
        run_id: UUID string of the run to check.
        user_id: UUID string from the validated JWT sub claim.
        request: FastAPI request — used to access app.state.db_engine.

    Raises:
        HTTPException 404: Run not found.
        HTTPException 403: Authenticated user does not own this run.
    """
    session_factory = async_sessionmaker(
        bind=request.app.state.db_engine,
        expire_on_commit=False,
        autoflush=False,
    )
    async with session_factory() as session:
        result = await session.execute(
            text("SELECT user_id FROM runs WHERE id = :run_id"),
            {"run_id": run_id},
        )
        row = result.fetchone()

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run {run_id} not found",
        )

    if str(row.user_id) != user_id:
        logger.warning(
            "sse.ownership_denied",
            run_id=run_id,
            requesting_user=user_id,
            run_owner=str(row.user_id),
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this run's stream",
        )


async def _proxy_stream(run_id: str) -> AsyncIterator[bytes]:
    """
    Open an httpx SSE connection to the Orchestrator and yield each chunk.

    Monitors event payloads for terminal event types (run_complete, run_error)
    and stops iteration after forwarding the terminal event, allowing the
    StreamingResponse to close the connection within one poll cycle.

    On Orchestrator connection failure, yields a single error SSE event
    and returns so the browser receives a clean close rather than a hang.

    Args:
        run_id: UUID of the orchestration run to stream.

    Yields:
        Raw SSE byte chunks forwarded from the Orchestrator.
    """
    orchestrator_url = f"{settings.orchestrator_url}/runs/{run_id}/stream"
    logger.info("sse.proxy_open", run_id=run_id, orchestrator_url=orchestrator_url)

    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(connect=5.0, read=300.0, write=5.0, pool=5.0)
        ) as client:
            async with client.stream("GET", orchestrator_url) as response:
                response.raise_for_status()
                async for chunk in response.aiter_bytes():
                    if not chunk:
                        continue

                    yield chunk
                    sse_events_emitted_total.labels(service="gateway", event_type="forwarded").inc()

                    # Check for terminal event to close stream promptly
                    try:
                        # SSE chunks are "data: <json>\n\n" — parse the JSON portion
                        text_chunk = chunk.decode("utf-8", errors="ignore")
                        for line in text_chunk.splitlines():
                            if line.startswith("data:"):
                                payload = json.loads(line[5:].strip())
                                if payload.get("event_type") in _TERMINAL_EVENT_TYPES:
                                    logger.info(
                                        "sse.terminal_event_received",
                                        run_id=run_id,
                                        event_type=payload.get("event_type"),
                                    )
                                    return  # closes the generator; StreamingResponse ends
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        # Non-JSON chunk (keepalive comment etc.) — continue streaming
                        pass

    except httpx.ConnectError as exc:
        logger.error("sse.orchestrator_unreachable", run_id=run_id, error=str(exc))
        error_event = 'data: {"event_type":"error","payload":{"message":"Orchestrator stream unavailable"}}\n\n'
        yield error_event.encode("utf-8")

    except httpx.HTTPStatusError as exc:
        logger.error("sse.orchestrator_http_error", run_id=run_id, status=exc.response.status_code)
        error_event = f'data: {{"event_type":"error","payload":{{"message":"Upstream error {exc.response.status_code}"}}}}\n\n'
        yield error_event.encode("utf-8")


@router.get(
    "/{run_id}",
    summary="Stream live thought-trace events for a run",
    response_class=StreamingResponse,
)
async def stream_run(
    run_id: str,
    request: Request,
    token: str = Query(
        ..., description="JWT access token — required because EventSource cannot set headers"
    ),
) -> StreamingResponse:
    """
    Proxy the Orchestrator's SSE stream for a single run to the browser.

    Authenticates via ?token= query parameter (EventSource API limitation).
    Enforces run ownership before opening the upstream connection.
    Increments/decrements sse_connections_active Prometheus gauge.

    Args:
        run_id: UUID of the orchestration run to stream.
        request: FastAPI request for app.state access.
        token: JWT string from ?token= query parameter.

    Returns:
        StreamingResponse with Content-Type: text/event-stream.

    Raises:
        HTTPException 401: Missing, invalid, or expired token.
        HTTPException 403: Token belongs to a different user than the run owner.
        HTTPException 404: Run does not exist.
    """
    redis_client: aioredis.Redis = request.app.state.redis

    # Step 1: Validate JWT and Redis session
    user_id = await _validate_token(token, redis_client)

    # Step 2: Ownership check
    await _verify_run_ownership(run_id, user_id, request)

    logger.info("sse.stream_open", run_id=run_id, user_id=user_id)
    sse_connections_active.labels(service="gateway").inc()

    async def _guarded_stream() -> AsyncIterator[bytes]:
        """Wrap _proxy_stream to ensure the gauge is decremented on close."""
        try:
            async for chunk in _proxy_stream(run_id):
                yield chunk
        finally:
            sse_connections_active.labels(service="gateway").dec()
            logger.info("sse.stream_closed", run_id=run_id, user_id=user_id)

    return StreamingResponse(
        _guarded_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
