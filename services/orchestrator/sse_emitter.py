# services/orchestrator/sse_emitter.py
"""
Redis pub/sub SSE emitter for the NEXUS Orchestrator.

Two public functions:

    emit_event()             — called by every orchestrator node to publish a
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

CRITICAL: The Redis client used here MUST be created with decode_responses=False
for pub/sub to work correctly. See _make_pubsub_client() below.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any, AsyncGenerator

import redis.asyncio as aioredis
import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from nodes.db import get_db_engine

logger = structlog.get_logger(__name__)

_TERMINAL_EVENTS: frozenset[str] = frozenset({"run_complete", "run_error"})
_EVENT_LIST_TTL_SECONDS: int = 60
_DONE_SENTINEL_TTL_SECONDS: int = 60
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

    # Persist event into Postgres (best-effort). Non-fatal: failures are logged
    # and the function continues to ensure SSE delivery is not blocked.
    try:
        engine = get_db_engine()
        if engine is not None:
            session_factory = async_sessionmaker(
                bind=engine,
                expire_on_commit=False,
                autoflush=False,
            )
            async with session_factory() as session:
                await session.execute(
                    text(
                        """
                        INSERT INTO events (run_id, type, payload, source)
                        VALUES (:run_id, :type, CAST(:payload AS jsonb), :source)
                        """
                    ),
                    {
                        "run_id": run_id,
                        "type": event_type,
                        "payload": json.dumps(payload),
                        "source": agent_name,
                    },
                )
                await session.commit()
            logger.info(
                "sse_event_persisted",
                run_id=run_id,
                event_type=event_type,
            )
    except Exception as exc:  # Non-fatal — continue to Redis publish
        logger.warning(
            "sse_event_persist_failed",
            run_id=run_id,
            event_type=event_type,
            error=str(exc),
        )

    try:
        subscriber_count = await redis_client.publish(channel, serialized)
        logger.info(
            "sse_event_published",
            run_id=run_id,
            event_type=event_type,
            channel=channel,
            subscriber_count=subscriber_count,
        )

        await redis_client.rpush(list_key, serialized)
        await redis_client.expire(list_key, _EVENT_LIST_TTL_SECONDS)

        if event_type in _TERMINAL_EVENTS:
            await redis_client.set(
                f"sse:done:{run_id}",
                event_type,
                ex=_DONE_SENTINEL_TTL_SECONDS,
            )
            logger.info(
                "sse_terminal_event_published",
                run_id=run_id,
                event_type=event_type,
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

    IMPORTANT: Uses pubsub.listen() — NOT pubsub.get_message() — because
    listen() is a true async generator that yields control to the event loop
    between messages. get_message() with timeout is synchronous blocking and
    will either block the event loop or silently drop messages.

    The pubsub client is created from the same Redis URL as the main client
    but as a separate connection, which is required for pub/sub.

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

    logger.info(
        "sse_subscriber_registered",
        run_id=run_id,
        channel=channel,
    )

    # ── Late-join: replay buffered events if run already completed ────────────
    try:
        done_value = await redis_client.get(done_key)
        if done_value:
            logger.info(
                "sse_stream_generator.late_join_replay",
                run_id=run_id,
                done_value=done_value,
            )
            buffered = await redis_client.lrange(list_key, 0, -1)
            for raw in buffered:
                try:
                    event_dict = json.loads(raw)
                    event_id += 1
                    sse_chunk = _format_sse(
                        event_type=event_dict.get("event_type", "event"),
                        data=event_dict,
                        event_id=event_id,
                    )
                    logger.debug(
                        "sse_stream_yield",
                        run_id=run_id,
                        event_id=event_id,
                        event_type=event_dict.get("event_type"),
                        source="replay",
                    )
                    yield sse_chunk
                except (json.JSONDecodeError, KeyError):
                    continue
            logger.info("sse_stream_generator.late_join_complete", run_id=run_id)
            return
    except Exception as exc:
        logger.warning(
            "sse_stream_generator.late_join_check_failed",
            run_id=run_id,
            error=str(exc),
        )

    # ── Live stream: subscribe to Redis pub/sub channel ───────────────────────
    # Create a dedicated pubsub object from the existing client.
    # CRITICAL: pubsub() on a decode_responses=True client still works for
    # pub/sub as long as we parse message["data"] carefully — but we explicitly
    # handle both bytes and str below.
    pubsub = redis_client.pubsub()

    try:
        await pubsub.subscribe(channel)
        logger.info(
            "sse_stream_generator.subscribed",
            run_id=run_id,
            channel=channel,
        )

        # Send an immediate confirmation event so the client knows the stream
        # is live — this also validates the connection before the first real event
        yield f": stream-open run_id={run_id}\n\n"

        last_heartbeat = time.monotonic()

        # Use listen() — the correct async pattern for redis.asyncio pub/sub.
        # listen() is an async generator that properly yields to the event loop.
        # We wrap it with asyncio.wait_for on each iteration for heartbeat support.
        async for message in _listen_with_heartbeat(
            pubsub=pubsub,
            run_id=run_id,
            heartbeat_interval=_HEARTBEAT_INTERVAL_SECONDS,
        ):
            if message is None:
                # Heartbeat timeout — yield keepalive comment
                yield ": heartbeat\n\n"
                logger.debug("sse_stream_generator.heartbeat", run_id=run_id)
                continue

            msg_type = message.get("type")

            # Skip subscription confirmation messages
            if msg_type in ("subscribe", "unsubscribe", "psubscribe", "punsubscribe"):
                continue

            if msg_type != "message":
                continue

            raw_data = message.get("data", "")

            # Handle both bytes (decode_responses=False) and str (decode_responses=True)
            if isinstance(raw_data, bytes):
                raw_data = raw_data.decode("utf-8", errors="ignore")

            if not raw_data:
                continue

            try:
                event_dict: dict[str, Any] = json.loads(raw_data)
            except (json.JSONDecodeError, ValueError) as exc:
                logger.warning(
                    "sse_stream_generator.parse_error",
                    run_id=run_id,
                    error=str(exc),
                    raw=raw_data[:100],
                )
                continue

            event_type = event_dict.get("event_type", "event")
            event_id += 1

            sse_chunk = _format_sse(
                event_type=event_type,
                data=event_dict,
                event_id=event_id,
            )

            logger.info(
                "sse_event_delivered",
                run_id=run_id,
                event_id=event_id,
                event_type=event_type,
            )

            logger.debug(
                "sse_stream_yield",
                run_id=run_id,
                event_id=event_id,
                event_type=event_type,
            )

            yield sse_chunk

            # Close stream after terminal event — yield first, then return
            if event_type in _TERMINAL_EVENTS:
                logger.info(
                    "sse_stream_generator.terminal_event_closing",
                    run_id=run_id,
                    event_type=event_type,
                    total_events=event_id,
                )
                return

    except GeneratorExit:
        logger.info("sse_stream_generator.client_disconnected", run_id=run_id)
    except asyncio.CancelledError:
        logger.info("sse_stream_generator.cancelled", run_id=run_id)
    except Exception as exc:
        logger.error(
            "sse_stream_generator.error",
            run_id=run_id,
            error=str(exc),
        )
    finally:
        try:
            await pubsub.unsubscribe(channel)
            await pubsub.close()
            logger.info(
                "sse_stream_generator.cleaned_up",
                run_id=run_id,
                total_events_delivered=event_id,
            )
        except Exception as exc:
            logger.warning(
                "sse_stream_generator.cleanup_error",
                run_id=run_id,
                error=str(exc),
            )


async def _listen_with_heartbeat(
    pubsub: aioredis.client.PubSub,
    run_id: str,
    heartbeat_interval: float,
) -> AsyncGenerator[dict[str, Any] | None, None]:
    """
    Wrap Redis pubsub.listen() with heartbeat timeout support.

    pubsub.listen() blocks indefinitely waiting for messages — we need
    periodic heartbeats to keep the HTTP connection alive through proxies.
    This wrapper uses asyncio.wait_for to impose a timeout on each message
    read, yielding None on timeout so the caller can send a keepalive.

    Args:
        pubsub: Active Redis PubSub object already subscribed to a channel.
        run_id: Run UUID for logging.
        heartbeat_interval: Seconds between heartbeats when no messages arrive.

    Yields:
        Message dict from Redis on message arrival, None on heartbeat timeout.
    """
    # get_message with timeout=heartbeat_interval is the correct pattern
    # when used as: await pubsub.get_message(ignore_subscribe_messages=False, timeout=N)
    # The timeout here is passed to the underlying socket recv, NOT asyncio.
    # To make this truly async-safe we use a manual asyncio.wait_for wrapper
    # around a task that reads from the pubsub.
    while True:
        try:
            message = await asyncio.wait_for(
                _get_next_message(pubsub),
                timeout=heartbeat_interval,
            )
            yield message
        except asyncio.TimeoutError:
            yield None
        except asyncio.CancelledError:
            logger.debug("_listen_with_heartbeat.cancelled", run_id=run_id)
            return
        except Exception as exc:
            logger.error(
                "_listen_with_heartbeat.error",
                run_id=run_id,
                error=str(exc),
            )
            return


async def _get_next_message(pubsub: aioredis.client.PubSub) -> dict[str, Any]:
    """
    Poll pubsub for the next message using a true async loop.

    pubsub.get_message() returns None immediately if no message is buffered.
    We loop with a short asyncio.sleep to yield control to the event loop
    between polls — this is the correct pattern for redis.asyncio pub/sub.

    This is NOT the same as passing timeout= to get_message(), which blocks
    the underlying socket and therefore the entire asyncio event loop.

    Args:
        pubsub: Active Redis PubSub object.

    Returns:
        The next message dict from Redis.
    """
    while True:
        # ignore_subscribe_messages=False so we see subscription confirmations
        # and can skip them explicitly in the caller
        message = await pubsub.get_message(
            ignore_subscribe_messages=False,
            timeout=None,
        )
        if message is not None:
            return message
        # Yield to event loop before next poll — prevents busy-spin
        await asyncio.sleep(0.05)