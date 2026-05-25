"""
Unit tests for services/orchestrator/sse_emitter.py.

All Redis calls are mocked. Tests run in isolation — no containers required.

Run:
    docker exec nexus-orchestrator python -m pytest tests/test_sse_emitter.py -v --asyncio-mode=auto
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sse_emitter import (
    _TERMINAL_EVENTS,
    _format_sse,
    emit_event,
    sse_stream_generator,
)

# ── Fixtures ──────────────────────────────────────────────────────────────────


def _mock_redis(
    done_value: str | None = None,
    buffered_events: list[str] | None = None,
) -> AsyncMock:
    """Return a mock async Redis client."""
    redis = AsyncMock()
    redis.publish = AsyncMock(return_value=1)
    redis.rpush = AsyncMock(return_value=1)
    redis.expire = AsyncMock(return_value=True)
    redis.set = AsyncMock(return_value=True)
    redis.get = AsyncMock(return_value=done_value)
    redis.lrange = AsyncMock(return_value=buffered_events or [])
    return redis


def _mock_pubsub(messages: list[dict]) -> AsyncMock:
    """Return a mock pubsub object that yields messages then None."""
    call_count = 0
    message_list = list(messages)

    pubsub = AsyncMock()
    pubsub.subscribe = AsyncMock()
    pubsub.unsubscribe = AsyncMock()
    pubsub.close = AsyncMock()

    async def get_message_side_effect(*args, **kwargs):
        nonlocal call_count
        if call_count < len(message_list):
            msg = message_list[call_count]
            call_count += 1
            return msg
        # After all messages, raise CancelledError to exit the loop
        raise asyncio.CancelledError()

    pubsub.get_message = get_message_side_effect
    return pubsub


# ── _format_sse tests ──────────────────────────────────────────────────────────


def test_format_sse_produces_correct_structure() -> None:
    """_format_sse produces W3C-compliant SSE string."""
    result = _format_sse("thought", {"content": "hello"}, 1)
    assert result.startswith("event: thought\n")
    assert "data: " in result
    assert '"content": "hello"' in result
    assert result.endswith("\n\n")
    assert "id: 1" in result


def test_format_sse_ends_with_double_newline() -> None:
    """SSE spec requires double newline to terminate each event block."""
    result = _format_sse("run_start", {}, 1)
    assert result[-2:] == "\n\n"


# ── emit_event tests ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_emit_event_calls_publish_and_rpush() -> None:
    """emit_event publishes to channel and appends to replay list."""
    redis = _mock_redis()
    await emit_event(
        run_id="run-001",
        event_type="thought",
        agent_name="orchestrator.decompose_query",
        payload={"content": "test"},
        redis_client=redis,
    )

    redis.publish.assert_awaited_once()
    publish_args = redis.publish.call_args[0]
    assert publish_args[0] == "sse:run-001"

    redis.rpush.assert_awaited_once()
    rpush_args = redis.rpush.call_args[0]
    assert rpush_args[0] == "sse:events:run-001"

    redis.expire.assert_awaited_once()


@pytest.mark.asyncio
async def test_emit_event_sets_done_sentinel_on_terminal_event() -> None:
    """emit_event sets sse:done:{run_id} for terminal event types."""
    for terminal_type in _TERMINAL_EVENTS:
        redis = _mock_redis()
        await emit_event(
            run_id="run-001",
            event_type=terminal_type,
            agent_name="orchestrator.finalize_run",
            payload={},
            redis_client=redis,
        )
        redis.set.assert_awaited()
        set_args = redis.set.call_args[0]
        assert set_args[0] == "sse:done:run-001"
        assert set_args[1] == terminal_type


@pytest.mark.asyncio
async def test_emit_event_does_not_set_done_sentinel_for_non_terminal() -> None:
    """emit_event does NOT set sse:done:{run_id} for non-terminal events."""
    redis = _mock_redis()
    await emit_event(
        run_id="run-001",
        event_type="thought",
        agent_name="orchestrator.decompose_query",
        payload={},
        redis_client=redis,
    )
    redis.set.assert_not_awaited()


@pytest.mark.asyncio
async def test_emit_event_swallows_redis_error() -> None:
    """emit_event does not raise when Redis publish fails."""
    redis = AsyncMock()
    redis.publish = AsyncMock(side_effect=Exception("Redis connection refused"))

    # Should not raise
    await emit_event(
        run_id="run-001",
        event_type="thought",
        agent_name="test",
        payload={},
        redis_client=redis,
    )


# ── sse_stream_generator tests ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_sse_stream_generator_late_join_replays_buffered_events() -> None:
    """Generator replays buffered events and closes when run already done."""
    buffered = [
        json.dumps(
            {
                "event_type": "run_start",
                "payload": {},
                "agent_name": "orchestrator",
                "run_id": "r1",
                "timestamp": 1.0,
            }
        ),
        json.dumps(
            {
                "event_type": "run_complete",
                "payload": {},
                "agent_name": "orchestrator",
                "run_id": "r1",
                "timestamp": 2.0,
            }
        ),
    ]
    redis = _mock_redis(done_value="run_complete", buffered_events=buffered)

    results = []
    async for chunk in sse_stream_generator("r1", redis):
        results.append(chunk)

    assert len(results) == 2
    assert "run_start" in results[0]
    assert "run_complete" in results[1]


@pytest.mark.asyncio
async def test_sse_stream_generator_yields_sse_formatted_events() -> None:
    """Generator yields properly formatted SSE strings from pub/sub messages."""
    event_payload = json.dumps(
        {
            "event_type": "thought",
            "payload": {"content": "planning"},
            "agent_name": "orchestrator.decompose_query",
            "run_id": "r1",
            "timestamp": 1.0,
        }
    ).encode()

    terminal_payload = json.dumps(
        {
            "event_type": "run_complete",
            "payload": {},
            "agent_name": "orchestrator.finalize_run",
            "run_id": "r1",
            "timestamp": 2.0,
        }
    ).encode()

    messages = [
        {"type": "message", "data": event_payload},
        {"type": "message", "data": terminal_payload},
    ]

    redis = _mock_redis()
    mock_pubsub = _mock_pubsub(messages)
    redis.pubsub = MagicMock(return_value=mock_pubsub)

    results = []
    async for chunk in sse_stream_generator("r1", redis):
        results.append(chunk)

    # Should have thought + run_complete
    assert any("thought" in r for r in results)
    assert any("run_complete" in r for r in results)
    for r in results:
        assert r.endswith("\n\n")


@pytest.mark.asyncio
async def test_sse_stream_generator_closes_after_terminal_event() -> None:
    """Generator stops yielding after run_complete event."""
    terminal_payload = json.dumps(
        {
            "event_type": "run_complete",
            "payload": {},
            "agent_name": "orchestrator.finalize_run",
            "run_id": "r1",
            "timestamp": 1.0,
        }
    ).encode()

    messages = [{"type": "message", "data": terminal_payload}]
    redis = _mock_redis()
    mock_pubsub = _mock_pubsub(messages)
    redis.pubsub = MagicMock(return_value=mock_pubsub)

    count = 0
    async for _ in sse_stream_generator("r1", redis):
        count += 1

    # Should yield the initial stream-open handshake and then the terminal event
    assert count == 2
    mock_pubsub.unsubscribe.assert_awaited()
    mock_pubsub.close.assert_awaited()


@pytest.mark.asyncio
async def test_sse_stream_generator_cleans_up_pubsub_on_cancel() -> None:
    """Generator calls unsubscribe and close when CancelledError is raised."""
    redis = _mock_redis()
    mock_pubsub = _mock_pubsub([])  # raises CancelledError immediately
    redis.pubsub = MagicMock(return_value=mock_pubsub)

    results = []
    async for chunk in sse_stream_generator("r1", redis):
        results.append(chunk)

    mock_pubsub.unsubscribe.assert_awaited()
    mock_pubsub.close.assert_awaited()


@pytest.mark.asyncio
async def test_emit_event_payload_is_valid_json() -> None:
    """Published message is valid JSON with all required fields."""
    redis = _mock_redis()
    await emit_event(
        run_id="run-json-001",
        event_type="thought",
        agent_name="test.node",
        payload={"key": "value"},
        redis_client=redis,
    )

    published_raw = redis.publish.call_args[0][1]
    parsed = json.loads(published_raw)
    assert parsed["event_type"] == "thought"
    assert parsed["agent_name"] == "test.node"
    assert parsed["run_id"] == "run-json-001"
    assert parsed["payload"] == {"key": "value"}
    assert "timestamp" in parsed
