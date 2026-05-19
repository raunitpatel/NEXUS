"""
Unit tests for services/code_agent/agent.py and executor.py.

All external dependencies (LLM provider, Kafka, subprocess) are mocked.
No Docker containers required for unit tests.

Run:
    docker exec nexus-code-agent python -m pytest tests/ -v --asyncio-mode=auto
"""

from __future__ import annotations

import subprocess
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from executor import CodeExecutor, ExecutionResult
from llm_provider import LLMResponse


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _llm_response(content: str, prompt_tokens: int = 50, completion_tokens: int = 20) -> LLMResponse:
    return LLMResponse(content=content, prompt_tokens=prompt_tokens, completion_tokens=completion_tokens)


def _base_run_kwargs() -> dict[str, Any]:
    return {
        "task_id": "task-001",
        "run_id": "run-001",
        "user_id": "user-001",
        "instruction": "Write a Python function that returns the Fibonacci sequence up to n, then call fib(10) and print the result.",
    }


# ── CodeExecutor tests ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_executor_success_exit_code_zero() -> None:
    """execute() returns exit_code=0 and captures stdout for valid code."""
    executor = CodeExecutor(timeout=10)
    result = await executor.execute("print(42)", language="python")

    assert result.exit_code == 0
    assert "42" in result.stdout
    assert result.stderr == ""


@pytest.mark.asyncio
async def test_executor_syntax_error_nonzero_exit() -> None:
    """execute() returns non-zero exit_code and stderr for invalid Python."""
    executor = CodeExecutor(timeout=10)
    result = await executor.execute("def broken(: pass", language="python")

    assert result.exit_code != 0
    assert result.stderr != ""


@pytest.mark.asyncio
async def test_executor_timeout_returns_exit_124() -> None:
    """execute() returns exit_code=124 when code exceeds timeout."""
    executor = CodeExecutor(timeout=1)
    result = await executor.execute("import time; time.sleep(5)", language="python")

    assert result.exit_code == 124
    assert "timed out" in result.stderr.lower()


@pytest.mark.asyncio
async def test_executor_unsupported_language_returns_error() -> None:
    """execute() returns exit_code=1 and helpful stderr for unsupported language."""
    executor = CodeExecutor(timeout=10)
    result = await executor.execute("console.log('hi')", language="javascript")

    assert result.exit_code == 1
    assert "unsupported" in result.stderr.lower()


@pytest.mark.asyncio
async def test_executor_stdout_captured() -> None:
    """execute() captures all print() output in stdout."""
    executor = CodeExecutor(timeout=10)
    result = await executor.execute("print('hello'); print('world')", language="python")

    assert result.exit_code == 0
    assert "hello" in result.stdout
    assert "world" in result.stdout


# ── CodeAgent._extract_code tests ─────────────────────────────────────────────

def test_extract_code_strips_python_fence() -> None:
    """_extract_code strips ```python ... ``` fences."""
    from agent import CodeAgent
    agent = CodeAgent.__new__(CodeAgent)  # skip __init__

    raw = "```python\nprint(42)\n```"
    assert agent._extract_code(raw) == "print(42)"


def test_extract_code_strips_plain_fence() -> None:
    """_extract_code strips ``` ... ``` fences without language tag."""
    from agent import CodeAgent
    agent = CodeAgent.__new__(CodeAgent)

    raw = "```\nprint(42)\n```"
    assert agent._extract_code(raw) == "print(42)"


def test_extract_code_no_fence_returns_stripped() -> None:
    """_extract_code returns raw code when no fence is present."""
    from agent import CodeAgent
    agent = CodeAgent.__new__(CodeAgent)

    raw = "  print(42)  "
    assert agent._extract_code(raw) == "print(42)"


# ── CodeAgent.run() tests ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_code_agent_success_on_first_iteration() -> None:
    """CodeAgent.run() returns success result when code works on first try."""
    from agent import CodeAgent

    mock_provider = AsyncMock()
    mock_provider.complete = AsyncMock(
        return_value=_llm_response("print(sum(range(11)))")
    )

    with (
        patch("agent.get_llm_provider", return_value=mock_provider),
        patch("agent.CodeAgent._publish_event", new_callable=AsyncMock),
    ):
        agent = CodeAgent()
        result = await agent.run(**_base_run_kwargs())

    assert result.exit_code == 0
    assert result.success is True
    assert result.iterations == 1
    assert "55" in result.stdout  # sum(0..10)
    mock_provider.complete.assert_awaited_once()  # only write_code, no fix_code


@pytest.mark.asyncio
async def test_code_agent_success_on_second_iteration() -> None:
    """CodeAgent.run() calls fix_code and succeeds on iteration 2."""
    from agent import CodeAgent

    mock_provider = AsyncMock()
    mock_provider.complete = AsyncMock(side_effect=[
        _llm_response("def broken(: pass"),       # iteration 1 — syntax error
        _llm_response("print(42)"),                # iteration 2 — fixed
    ])

    with (
        patch("agent.get_llm_provider", return_value=mock_provider),
        patch("agent.CodeAgent._publish_event", new_callable=AsyncMock),
    ):
        agent = CodeAgent()
        result = await agent.run(**_base_run_kwargs())

    assert result.exit_code == 0
    assert result.iterations == 2
    assert mock_provider.complete.await_count == 2


@pytest.mark.asyncio
async def test_code_agent_exhausts_max_iterations() -> None:
    """CodeAgent.run() stops at max_iterations even if code never passes."""
    from agent import CodeAgent

    mock_provider = AsyncMock()
    # Always returns broken code
    mock_provider.complete = AsyncMock(return_value=_llm_response("this is not python"))

    with (
        patch("agent.get_llm_provider", return_value=mock_provider),
        patch("agent.CodeAgent._publish_event", new_callable=AsyncMock),
        patch("agent.settings") as mock_settings,
    ):
        mock_settings.max_iterations = 3
        mock_settings.execution_timeout_seconds = 10
        mock_settings.kafka_bootstrap_servers = "kafka:9092"
        mock_settings.kafka_topic_events = "nexus.events"

        agent = CodeAgent()
        result = await agent.run(**_base_run_kwargs())

    assert result.iterations == 3
    assert result.exit_code != 0
    assert result.success is False
    assert mock_provider.complete.await_count == 3


@pytest.mark.asyncio
async def test_code_agent_publishes_correct_number_of_events() -> None:
    """CodeAgent.run() publishes agent_start + N code_iteration + agent_end events."""
    from agent import CodeAgent

    mock_provider = AsyncMock()
    mock_provider.complete = AsyncMock(return_value=_llm_response("print(1)"))

    published_events: list[str] = []

    async def capture_publish(**kwargs: Any) -> None:
        published_events.append(str(kwargs.get("event_type", "")))

    with (
        patch("agent.get_llm_provider", return_value=mock_provider),
        patch("agent.CodeAgent._publish_event", side_effect=capture_publish),
    ):
        agent = CodeAgent()
        await agent.run(**_base_run_kwargs())

    # agent_start, code_iteration (1), agent_end
    assert published_events[0] == "agent_start"
    assert "code_iteration" in published_events
    assert published_events[-1] == "agent_end"


@pytest.mark.asyncio
async def test_code_agent_llm_error_returns_error_result() -> None:
    """LLMProviderError on write_code returns CodeAgentResult with non-zero exit_code."""
    from agent import CodeAgent
    from llm_provider import LLMProviderError

    mock_provider = AsyncMock()
    mock_provider.complete = AsyncMock(
        side_effect=LLMProviderError("claude", "Connection refused")
    )

    with (
        patch("agent.get_llm_provider", return_value=mock_provider),
        patch("agent.CodeAgent._publish_event", new_callable=AsyncMock),
    ):
        agent = CodeAgent()
        result = await agent.run(**_base_run_kwargs())

    assert result.exit_code == 1
    assert result.success is False
    assert "LLM provider error" in result.stderr


@pytest.mark.asyncio
async def test_code_agent_result_to_dict_has_required_fields() -> None:
    """CodeAgentResult.to_dict() contains all required response fields."""
    from agent import CodeAgent

    mock_provider = AsyncMock()
    mock_provider.complete = AsyncMock(return_value=_llm_response("print('ok')"))

    with (
        patch("agent.get_llm_provider", return_value=mock_provider),
        patch("agent.CodeAgent._publish_event", new_callable=AsyncMock),
    ):
        agent = CodeAgent()
        result = await agent.run(**_base_run_kwargs())

    d = result.to_dict()
    assert "code" in d
    assert "stdout" in d
    assert "stderr" in d
    assert "exit_code" in d
    assert "iterations" in d
    assert "success" in d


@pytest.mark.asyncio
async def test_code_agent_strips_markdown_from_llm_output() -> None:
    """LLM code wrapped in ```python fences is correctly stripped before execution."""
    from agent import CodeAgent

    markdown_code = "```python\nprint('stripped')\n```"
    mock_provider = AsyncMock()
    mock_provider.complete = AsyncMock(return_value=_llm_response(markdown_code))

    with (
        patch("agent.get_llm_provider", return_value=mock_provider),
        patch("agent.CodeAgent._publish_event", new_callable=AsyncMock),
    ):
        agent = CodeAgent()
        result = await agent.run(**_base_run_kwargs())

    assert result.exit_code == 0
    assert "stripped" in result.stdout


# ── main.py endpoint tests ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_run_endpoint_missing_instruction_returns_error() -> None:
    """POST /run with empty input.instruction returns RunResponse with error."""
    from main import app
    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        response = client.post("/run", json={
            "run_id": "r1", "task_id": "t1", "user_id": "u1",
            "task_type": "code", "input": {}, "attempt": 1,
        })

    assert response.status_code == 200
    data = response.json()
    assert data["error"] == "input.instruction is required"
    assert data["output"] is None


@pytest.mark.asyncio
async def test_healthz_returns_ok() -> None:
    """GET /healthz returns 200 with status ok."""
    from main import app
    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}