"""
Redis pub/sub SSE emitter for the NEXUS Orchestrator.

Two public functions:

    emit_event()        — called by every orchestrator node to publish a
                            structured event to the Redis channel sse:{run_id}.
                            Also appends the serialized event to the Redis LIST
                            sse:events:{run_id} (60s TTL) so late-joining clients
                            can replay missed events.

    sse_stream_generator()   — async generator that subscribes to sse:{run_id},
                            yields SSE-formatted strings, sends a heartbeat every
                            15 seconds on idle, and closes cleanly on terminal
                            events (run_complete / run_error) or client disconnect.

Redis key schema:
    sse:{run_id}             — pub/sub channel (ephemeral)
    sse:events:{run_id}      — LIST of serialized JSON events (TTL 60s, for replay)
    sse:done:{run_id}        — STRING sentinel set by finalize_run (TTL 60s)

Usage (from a node):
    from sse_emitter import emit_event
    await emit_event(run_id=run_id, event_type="thought", agent_name="orchestrator",
                    payload={"content": "..."}, redis_client=redis)

Usage (from routers/sse.py):
    from sse_emitter import sse_stream_generator
    return StreamingResponse(sse_stream_generator(run_id, redis), media_type="text/event-stream")
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any, AsyncGenerator

import redis.asyncio as aioredis
import structlog

logger = structlog.get_logger(__name__)

# Terminal event types that close the SSE stream
_TERMINAL_EVENTS: frozenset[str] = frozenset({"run_complete", "run_error"})

# Redis key TTLs
_EVENT_LIST_TTL_SECONDS: int = 60
_DONE_SENTINEL_TTL_SECONDS: int = 60

# Heartbeat interval — must be less than any proxy/browser idle timeout
_HEARTBEAT_INTERVAL_SECONDS: float = 15.0


async def emit_event(
    run_id: str,
    event_type: str,
    agent_name: str,
    payload: dict[str, Any],
    redis_client: aioredis.Redis,
) -> None:
    """
    Publish a structured event to the Redis SSE channel for a run.

    Serializes the event to JSON, publishes to the pub/sub channel
    sse:{run_id}, and appends to the replay LIST sse:events:{run_id}.
    If event_type is a terminal type (run_complete, run_error), also sets
    the sse:done:{run_id} sentinel key so late-joining clients can detect
    the run has already finished.

    Failures are logged at WARNING level and swallowed — must never abort
    an orchestrator node execution.

    Args:
        run_id: UUID of the orchestration run.
        event_type: Semantic event type string (e.g. "thought", "run_start").
                    Should match EventType in shared/kafka_schemas.py.
        agent_name: Dotted source identifier (e.g. "orchestrator.decompose_query").
        payload: Arbitrary JSON-serializable dict for the event body.
        redis_client: Async Redis client from app.state.redis.
    """
    event_dict: dict[str, Any] = {
        "event_type": event_type,
        "agent_name": agent_name,
        "payload": payload,
        "timestamp": time.time(),
        "run_id": run_id,
    }
    serialized = json.dumps(event_dict)
    channel = f"sse:{run_id}"
    list_key = f"sse:events:{run_id}"

    try:
        # Publish to pub/sub subscribers (connected SSE clients)
        await redis_client.publish(channel, serialized)

        # Append to replay list for late-joining clients
        await redis_client.rpush(list_key, serialized)
        await redis_client.expire(list_key, _EVENT_LIST_TTL_SECONDS)

        # Set done sentinel for terminal events
        if event_type in _TERMINAL_EVENTS:
            await redis_client.set(
                f"sse:done:{run_id}",
                event_type,
                ex=_DONE_SENTINEL_TTL_SECONDS,
            )

        logger.debug(
            "sse_emitter.published",
            run_id=run_id,
            event_type=event_type,
            channel=channel,
        )

    except Exception as exc:
        logger.warning(
            "sse_emitter.publish_failed",
            run_id=run_id,
            event_type=event_type,
            error=str(exc),
        )


def _format_sse(event_type: str, data: dict[str, Any], event_id: int) -> str:
    """
    Format an event dict as an SSE-compliant string.

    Output format per W3C SSE spec:
        event: TYPE\\n
        data: {JSON}\\n
        id: N\\n
        \\n

    Args:
        event_type: SSE event type field value.
        data: Dict to serialize as the data field.
        event_id: Monotonically increasing integer for the id field.

    Returns:
        SSE-formatted string ready to yield to StreamingResponse.
    """
    return f"event: {event_type}\ndata: {json.dumps(data)}\nid: {event_id}\n\n"


async def sse_stream_generator(
    run_id: str,
    redis_client: aioredis.Redis,
) -> AsyncGenerator[str, None]:
    """
    Async generator that streams SSE events for a run to an HTTP client.

    Subscribes to the Redis pub/sub channel sse:{run_id}. For each published
    message, yields a W3C SSE-formatted string. Sends a heartbeat comment
    every _HEARTBEAT_INTERVAL_SECONDS seconds when no messages arrive.
    Closes (returns) when a terminal event is received or the client
    disconnects (GeneratorExit / asyncio.CancelledError).

    Late-join handling: checks sse:done:{run_id} before subscribing. If set,
    replays all events from sse:events:{run_id} LIST and closes immediately.

    Args:
        run_id: UUID of the orchestration run to stream events for.
        redis_client: Async Redis client from app.state.redis.

    Yields:
        SSE-formatted strings (event + data + id blocks, heartbeat comments).
    """
    event_id: int = 0
    channel = f"sse:{run_id}"
    done_key = f"sse:done:{run_id}"
    list_key = f"sse:events:{run_id}"

    logger.info("sse_stream_generator.start", run_id=run_id)

    # Late-join: if run already completed, replay buffered events and close
    try:
        done_value = await redis_client.get(done_key)
        if done_value:
            logger.info("sse_stream_generator.late_join_replay", run_id=run_id)
            buffered = await redis_client.lrange(list_key, 0, -1)
            for raw in buffered:
                try:
                    event_dict = json.loads(raw)
                    event_id += 1
                    yield _format_sse(
                        event_type=event_dict.get("event_type", "event"),
                        data=event_dict,
                        event_id=event_id,
                    )
                except (json.JSONDecodeError, KeyError):
                    continue
            logger.info("sse_stream_generator.late_join_complete", run_id=run_id)
            return
    except Exception as exc:
        logger.warning("sse_stream_generator.late_join_check_failed", run_id=run_id, error=str(exc))

    # Subscribe to live events
    pubsub = redis_client.pubsub()

    try:
        await pubsub.subscribe(channel)
        logger.info("sse_stream_generator.subscribed", run_id=run_id, channel=channel)

        while True:
            try:
                # Non-blocking get with heartbeat timeout
                message = await asyncio.wait_for(
                    pubsub.get_message(ignore_subscribe_messages=True, timeout=0.1),
                    timeout=_HEARTBEAT_INTERVAL_SECONDS,
                )
            except asyncio.TimeoutError:
                # Send heartbeat to keep connection alive through proxies
                yield ": heartbeat\n\n"
                continue
            except asyncio.CancelledError:
                logger.info("sse_stream_generator.cancelled", run_id=run_id)
                break

            if message is None:
                # No message yet — continue polling
                await asyncio.sleep(0.05)
                continue

            if message.get("type") != "message":
                continue

            try:
                event_dict: dict[str, Any] = json.loads(message["data"])
            except (json.JSONDecodeError, KeyError) as exc:
                logger.warning("sse_stream_generator.parse_error", run_id=run_id, error=str(exc))
                continue

            event_type = event_dict.get("event_type", "event")
            event_id += 1

            yield _format_sse(
                event_type=event_type,
                data=event_dict,
                event_id=event_id,
            )

            # Close stream on terminal event
            if event_type in _TERMINAL_EVENTS:
                logger.info(
                    "sse_stream_generator.terminal_event",
                    run_id=run_id,
                    event_type=event_type,
                )
                break

    except GeneratorExit:
        logger.info("sse_stream_generator.client_disconnected", run_id=run_id)
    except Exception as exc:
        logger.error("sse_stream_generator.error", run_id=run_id, error=str(exc))
    finally:
        try:
            await pubsub.unsubscribe(channel)
            await pubsub.close()
            logger.info("sse_stream_generator.cleaned_up", run_id=run_id)
        except Exception as exc:
            logger.warning("sse_stream_generator.cleanup_error", run_id=run_id, error=str(exc))