"""
SSE router for the NEXUS Orchestrator.

Exposes GET /runs/{run_id}/stream — streams real-time thought trace events
to connected clients via Server-Sent Events.

This endpoint is consumed by:
  - The API Gateway's SSE proxy router (services/gateway/routers/sse.py)
  - Direct curl connections during development

The response is a text/event-stream with:
  - One SSE event per orchestrator node state change
  - A heartbeat comment (': heartbeat') every 15 seconds
  - Stream closes after run_complete or run_error event
"""

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from sse_emitter import sse_stream_generator

logger = structlog.get_logger(__name__)
router = APIRouter()


@router.get(
    "/runs/{run_id}/stream",
    summary="Stream real-time SSE events for an orchestration run",
    response_class=StreamingResponse,
)
async def stream_run_events(run_id: str, request: Request) -> StreamingResponse:
    """
    Subscribe to real-time SSE events for the given run.

    Returns a text/event-stream response backed by the Redis pub/sub
    channel sse:{run_id}. Each event follows W3C SSE format:
        event: TYPE\\n
        data: {JSON}\\n
        id: N\\n
        \\n

    The stream closes automatically after receiving a run_complete or
    run_error event. Heartbeats are sent every 15 seconds.

    Args:
        run_id: UUID of the orchestration run to stream.
        request: FastAPI Request for accessing app.state.redis.

    Returns:
        StreamingResponse with Content-Type: text/event-stream.
    """
    redis = request.app.state.redis

    logger.info("sse.stream_requested", run_id=run_id)

    return StreamingResponse(
        sse_stream_generator(run_id=run_id, redis_client=redis),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # Disable NGINX buffering for SSE
            "Connection": "keep-alive",
        },
    )