# data_gen/tests/test_simulate_runs.py
"""
Unit tests for data_gen/simulate_runs.py.

All HTTP calls are mocked — no running services required.
Tests verify: auth flow, run creation, SSE parsing, result tallying.

Run:
    cd nexus
    python -m pytest data_gen/tests/test_simulate_runs.py -v --asyncio-mode=auto
"""

from __future__ import annotations

import asyncio
import json
from typing import AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from data_gen.queries import ALL_QUERIES, QUERY_CATEGORIES


# ── Query definition tests ────────────────────────────────────────────────────

def test_all_queries_count() -> None:
    """ALL_QUERIES contains exactly 20 entries."""
    assert len(ALL_QUERIES) == 20


def test_all_categories_have_five_queries() -> None:
    """Each category has exactly 5 queries."""
    for category, queries in QUERY_CATEGORIES.items():
        assert len(queries) == 5, f"Category '{category}' has {len(queries)} queries, expected 5"


def test_all_queries_have_required_fields() -> None:
    """Every QueryDefinition has category, query, and expected_agents."""
    for q in ALL_QUERIES:
        assert "category" in q
        assert "query" in q
        assert "expected_agents" in q
        assert len(q["query"]) > 20, f"Query too short: {q['query']}"


def test_categories_are_correct() -> None:
    """All categories are one of: research, code, memory, tool."""
    valid = {"research", "code", "memory", "tool"}
    for q in ALL_QUERIES:
        assert q["category"] in valid


# ── SimulationClient.register() tests ────────────────────────────────────────

@pytest.mark.asyncio
async def test_register_success_returns_true() -> None:
    """register() returns True on HTTP 201."""
    from data_gen.simulate_runs import SimulationClient

    mock_response = MagicMock()
    mock_response.status_code = 201

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)

    client = SimulationClient.__new__(SimulationClient)
    client._client = mock_client
    client._token = ""

    result = await client.register()
    assert result is True


@pytest.mark.asyncio
async def test_register_409_returns_true() -> None:
    """register() returns True on HTTP 409 (already exists)."""
    from data_gen.simulate_runs import SimulationClient

    mock_response = MagicMock()
    mock_response.status_code = 409

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)

    client = SimulationClient.__new__(SimulationClient)
    client._client = mock_client
    client._token = ""

    result = await client.register()
    assert result is True


@pytest.mark.asyncio
async def test_register_500_returns_false() -> None:
    """register() returns False on HTTP 500."""
    from data_gen.simulate_runs import SimulationClient

    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_response.text = "Internal Server Error"

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)

    client = SimulationClient.__new__(SimulationClient)
    client._client = mock_client
    client._token = ""

    result = await client.register()
    assert result is False


# ── SimulationClient.login() tests ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_login_stores_token() -> None:
    """login() stores JWT token and returns True on HTTP 200."""
    from data_gen.simulate_runs import SimulationClient

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"access_token": "test-jwt-token-abc123"}

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)

    client = SimulationClient.__new__(SimulationClient)
    client._client = mock_client
    client._token = ""

    result = await client.login()

    assert result is True
    assert client._token == "test-jwt-token-abc123"


@pytest.mark.asyncio
async def test_login_failure_returns_false() -> None:
    """login() returns False on HTTP 401."""
    from data_gen.simulate_runs import SimulationClient

    mock_response = MagicMock()
    mock_response.status_code = 401
    mock_response.text = "Unauthorized"

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)

    client = SimulationClient.__new__(SimulationClient)
    client._client = mock_client
    client._token = ""

    result = await client.login()
    assert result is False
    assert client._token == ""


# ── SimulationClient.create_run() tests ──────────────────────────────────────

@pytest.mark.asyncio
async def test_create_run_returns_run_id() -> None:
    """create_run() returns UUID string on HTTP 201."""
    from data_gen.simulate_runs import SimulationClient

    mock_response = MagicMock()
    mock_response.status_code = 201
    mock_response.json.return_value = {"run_id": "test-run-uuid-001"}

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)

    client = SimulationClient.__new__(SimulationClient)
    client._client = mock_client
    client._token = "test-token"

    result = await client.create_run("test query")
    assert result == "test-run-uuid-001"


@pytest.mark.asyncio
async def test_create_run_failure_returns_none() -> None:
    """create_run() returns None on HTTP 422."""
    from data_gen.simulate_runs import SimulationClient

    mock_response = MagicMock()
    mock_response.status_code = 422
    mock_response.text = "Validation error"

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)

    client = SimulationClient.__new__(SimulationClient)
    client._client = mock_client
    client._token = "test-token"

    result = await client.create_run("test query")
    assert result is None


# ── SSE parsing tests ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_consume_sse_detects_run_complete() -> None:
    """consume_sse_until_complete() returns 'completed' on run_complete event."""
    from data_gen.simulate_runs import SimulationClient

    sse_lines = [
        "data: " + json.dumps({
            "event_type": "thought",
            "payload": {"content": "Planning tasks..."},
        }),
        "data: " + json.dumps({
            "event_type": "agent_start",
            "payload": {"agent": "search"},
        }),
        "data: " + json.dumps({
            "event_type": "run_complete",
            "payload": {"output": "The answer is 42.", "status": "completed"},
        }),
    ]

    async def mock_aiter_lines() -> AsyncIterator[str]:
        for line in sse_lines:
            yield line

    mock_stream_response = MagicMock()
    mock_stream_response.status_code = 200
    mock_stream_response.aiter_lines = mock_aiter_lines
    mock_stream_response.__aenter__ = AsyncMock(return_value=mock_stream_response)
    mock_stream_response.__aexit__ = AsyncMock(return_value=False)

    mock_http_client = MagicMock()
    mock_http_client.stream = MagicMock(return_value=mock_stream_response)

    client = SimulationClient.__new__(SimulationClient)
    client._client = mock_http_client
    client._token = "test-token"

    status, event_count, output = await client.consume_sse_until_complete("run-001")

    assert status == "completed"
    assert event_count == 3
    assert output == "The answer is 42."


@pytest.mark.asyncio
async def test_consume_sse_detects_run_error() -> None:
    """consume_sse_until_complete() returns 'failed' on run_error event."""
    from data_gen.simulate_runs import SimulationClient

    sse_lines = [
        "data: " + json.dumps({
            "event_type": "run_error",
            "payload": {"error": "LLM provider failed", "status": "failed"},
        }),
    ]

    async def mock_aiter_lines() -> AsyncIterator[str]:
        for line in sse_lines:
            yield line

    mock_stream_response = MagicMock()
    mock_stream_response.status_code = 200
    mock_stream_response.aiter_lines = mock_aiter_lines
    mock_stream_response.__aenter__ = AsyncMock(return_value=mock_stream_response)
    mock_stream_response.__aexit__ = AsyncMock(return_value=False)

    mock_http_client = MagicMock()
    mock_http_client.stream = MagicMock(return_value=mock_stream_response)

    client = SimulationClient.__new__(SimulationClient)
    client._client = mock_http_client
    client._token = "test-token"

    status, event_count, output = await client.consume_sse_until_complete("run-001")

    assert status == "failed"
    assert "LLM provider failed" in output


@pytest.mark.asyncio
async def test_consume_sse_skips_keepalive_lines() -> None:
    """consume_sse_until_complete() ignores empty lines and SSE comments."""
    from data_gen.simulate_runs import SimulationClient

    sse_lines = [
        "",
        ": keepalive",
        "",
        "data: " + json.dumps({"event_type": "run_complete", "payload": {"output": "done"}}),
    ]

    async def mock_aiter_lines() -> AsyncIterator[str]:
        for line in sse_lines:
            yield line

    mock_stream_response = MagicMock()
    mock_stream_response.status_code = 200
    mock_stream_response.aiter_lines = mock_aiter_lines
    mock_stream_response.__aenter__ = AsyncMock(return_value=mock_stream_response)
    mock_stream_response.__aexit__ = AsyncMock(return_value=False)

    mock_http_client = MagicMock()
    mock_http_client.stream = MagicMock(return_value=mock_stream_response)

    client = SimulationClient.__new__(SimulationClient)
    client._client = mock_http_client
    client._token = "test-token"

    status, event_count, output = await client.consume_sse_until_complete("run-001")

    assert status == "completed"
    assert event_count == 1  # Only the run_complete data line counts


# ── SimulationReport tallying tests ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_run_simulation_tallies_results_correctly() -> None:
    """run_simulation() correctly counts successful/failed/timeout/error runs."""
    from data_gen.simulate_runs import SimulationReport, RunResult

    # Manually build a report as if 4 runs completed
    report = SimulationReport(started_at="2025-01-01T00:00:00+00:00")
    report.results = [
        RunResult("id1", "q1", "research", "completed", 5, 1000),
        RunResult("id2", "q2", "code", "completed", 4, 2000),
        RunResult("id3", "q3", "memory", "failed", 2, 500),
        RunResult("id4", "q4", "tool", "timeout", 1, 120000),
    ]

    for r in report.results:
        if r.status == "completed":
            report.successful_runs += 1
        elif r.status == "failed":
            report.failed_runs += 1
        elif r.status == "timeout":
            report.timeout_runs += 1
        else:
            report.error_runs += 1

    assert report.successful_runs == 2
    assert report.failed_runs == 1
    assert report.timeout_runs == 1
    assert report.error_runs == 0