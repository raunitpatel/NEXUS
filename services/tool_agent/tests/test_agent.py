"""
Unit tests for services/tool_agent/agent.py, tools/, and llm_provider.py.

All external dependencies (LLM, HTTP APIs, DB, Kafka) are mocked.
No Docker containers required for unit tests.

Run:
    docker exec nexus-tool-agent python -m pytest tests/ -v --asyncio-mode=auto
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from llm_provider import LLMResponse, ToolCallResult, get_tool_definitions

# ── Fixtures ──────────────────────────────────────────────────────────────────


def _tool_call_result(
    tool_name: str | None = "calculator",
    tool_input: dict | None = None,
    prompt_tokens: int = 100,
    completion_tokens: int = 30,
    raw_text: str = "",
) -> ToolCallResult:
    return ToolCallResult(
        tool_name=tool_name,
        tool_input=tool_input or {"expression": "137 * 42"},
        stop_reason="tool_use" if tool_name else "end_turn",
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        raw_text=raw_text,
    )


def _llm_response(
    content: str, prompt_tokens: int = 50, completion_tokens: int = 20
) -> LLMResponse:
    return LLMResponse(
        content=content, prompt_tokens=prompt_tokens, completion_tokens=completion_tokens
    )


# ── get_tool_definitions tests ────────────────────────────────────────────────


def test_get_tool_definitions_returns_three_tools() -> None:
    """get_tool_definitions() returns exactly 3 tool dicts."""
    tools = get_tool_definitions()
    assert len(tools) == 3


def test_get_tool_definitions_has_required_fields() -> None:
    """Each tool definition has 'name', 'description', 'input_schema'."""
    tools = get_tool_definitions()
    for tool in tools:
        assert "name" in tool
        assert "description" in tool
        assert "input_schema" in tool
        assert "properties" in tool["input_schema"]
        assert "required" in tool["input_schema"]


def test_get_tool_definitions_names_match_schema() -> None:
    """Tool names are exactly: calculator, get_weather, wikipedia_search."""
    names = {t["name"] for t in get_tool_definitions()}
    assert names == {"calculator", "get_weather", "wikipedia_search"}


# ── CalculatorTool tests ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_calculator_basic_multiplication() -> None:
    """CalculatorTool returns correct result for multiplication."""
    from tools.calculator import CalculatorTool

    result = await CalculatorTool().run("137 * 42")
    assert result["result"] == 5754
    assert result["expression"] == "137 * 42"


@pytest.mark.asyncio
async def test_calculator_complex_expression() -> None:
    """CalculatorTool handles parentheses and order of operations."""
    from tools.calculator import CalculatorTool

    result = await CalculatorTool().run("(100 + 50) / 3")
    assert abs(result["result"] - 50.0) < 0.001


@pytest.mark.asyncio
async def test_calculator_division_by_zero() -> None:
    """CalculatorTool returns error dict on division by zero."""
    from tools.calculator import CalculatorTool

    result = await CalculatorTool().run("10 / 0")
    assert "error" in result
    assert "zero" in result["error"].lower()


@pytest.mark.asyncio
async def test_calculator_invalid_expression() -> None:
    """CalculatorTool returns error dict on invalid input."""
    from tools.calculator import CalculatorTool

    result = await CalculatorTool().run("import os")
    assert "error" in result


@pytest.mark.asyncio
async def test_calculator_returns_int_for_whole_numbers() -> None:
    """CalculatorTool returns int (not float) for whole number results."""
    from tools.calculator import CalculatorTool

    result = await CalculatorTool().run("10 * 10")
    assert result["result"] == 100
    assert isinstance(result["result"], int)


# ── WeatherTool tests ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_weather_tool_returns_temperature() -> None:
    """WeatherTool returns dict with temperature_celsius key."""
    from tools.weather import WeatherTool

    mock_geocode_response = MagicMock()
    mock_geocode_response.status_code = 200
    mock_geocode_response.json.return_value = {
        "results": [{"latitude": 51.5, "longitude": -0.12, "name": "London"}]
    }
    mock_geocode_response.raise_for_status = MagicMock()

    mock_weather_response = MagicMock()
    mock_weather_response.status_code = 200
    mock_weather_response.json.return_value = {
        "current": {"temperature_2m": 15.3, "wind_speed_10m": 12.0, "weather_code": 3}
    }
    mock_weather_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(side_effect=[mock_geocode_response, mock_weather_response])

    with patch("tools.weather.httpx.AsyncClient", return_value=mock_client):
        result = await WeatherTool().run("London")

    assert result["city"] == "London"
    assert result["temperature_celsius"] == 15.3
    assert result["wind_speed_kmh"] == 12.0


@pytest.mark.asyncio
async def test_weather_tool_city_not_found() -> None:
    """WeatherTool returns error dict when city geocoding returns no results."""
    from tools.weather import WeatherTool

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"results": []}
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=mock_response)

    with patch("tools.weather.httpx.AsyncClient", return_value=mock_client):
        result = await WeatherTool().run("ZZZnonexistentcityZZZ")

    assert "error" in result


# ── WikipediaTool tests ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_wikipedia_tool_returns_summary() -> None:
    """WikipediaTool returns dict with title and summary."""
    from tools.wikipedia import WikipediaTool

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "title": "Hamlet",
        "extract": "Hamlet is a tragedy written by William Shakespeare.",
        "content_urls": {"desktop": {"page": "https://en.wikipedia.org/wiki/Hamlet"}},
    }
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=mock_response)

    with patch("tools.wikipedia.httpx.AsyncClient", return_value=mock_client):
        result = await WikipediaTool().run("Hamlet Shakespeare")

    assert result["title"] == "Hamlet"
    assert "Shakespeare" in result["summary"]
    assert result["url"] != ""


@pytest.mark.asyncio
async def test_wikipedia_tool_api_error_returns_error_dict() -> None:
    """WikipediaTool returns error dict when API raises RequestError."""
    import httpx
    from tools.wikipedia import WikipediaTool

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(side_effect=httpx.RequestError("Connection refused"))

    with patch("tools.wikipedia.httpx.AsyncClient", return_value=mock_client):
        result = await WikipediaTool().run("test query")

    assert "error" in result


# ── ToolAgent.run() tests ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_tool_agent_calculator_end_to_end() -> None:
    """ToolAgent.run() with calculator instruction returns answer with result."""
    from agent import ToolAgent

    mock_provider = AsyncMock()
    mock_provider.complete_with_tools = AsyncMock(
        return_value=_tool_call_result("calculator", {"expression": "137 * 42"})
    )
    mock_provider.complete = AsyncMock(
        return_value=_llm_response("137 multiplied by 42 equals 5754.")
    )

    with (
        patch("agent.get_llm_provider", return_value=mock_provider),
        patch("agent.ToolAgent._persist_tool_result", new_callable=AsyncMock),
        patch("agent.ToolAgent._publish_event", new_callable=AsyncMock),
        patch(
            "agent.CalculatorTool.run",
            new_callable=AsyncMock,
            return_value={"result": 5754, "expression": "137 * 42"},
        ),
    ):
        agent = ToolAgent(db_engine=None)
        result = await agent.run(
            task_id="t1",
            run_id="r1",
            user_id="u1",
            instruction="What is 137 * 42?",
        )

    assert result.tool_used == "calculator"
    assert result.error is None
    assert "5754" in result.answer


@pytest.mark.asyncio
async def test_tool_agent_no_tool_call_returns_direct_answer() -> None:
    """ToolAgent.run() returns LLM raw_text when no tool call is made."""
    from agent import ToolAgent

    mock_provider = AsyncMock()
    mock_provider.complete_with_tools = AsyncMock(
        return_value=_tool_call_result(
            tool_name=None,
            tool_input={},
            raw_text="I can answer this directly: Hello World.",
        )
    )

    with (
        patch("agent.get_llm_provider", return_value=mock_provider),
        patch("agent.ToolAgent._publish_event", new_callable=AsyncMock),
    ):
        agent = ToolAgent(db_engine=None)
        result = await agent.run(
            task_id="t1",
            run_id="r1",
            user_id="u1",
            instruction="Say hello world.",
        )

    assert result.tool_used is None
    assert "Hello World" in result.answer
    assert result.error is None


@pytest.mark.asyncio
async def test_tool_agent_llm_dispatch_failure_returns_error() -> None:
    """ToolAgent.run() returns error result when LLM dispatch raises LLMProviderError."""
    from agent import ToolAgent
    from llm_provider import LLMProviderError

    mock_provider = AsyncMock()
    mock_provider.complete_with_tools = AsyncMock(
        side_effect=LLMProviderError("claude", "Connection refused")
    )

    with (
        patch("agent.get_llm_provider", return_value=mock_provider),
        patch("agent.ToolAgent._publish_event", new_callable=AsyncMock),
    ):
        agent = ToolAgent(db_engine=None)
        result = await agent.run(
            task_id="t1",
            run_id="r1",
            user_id="u1",
            instruction="What is 2 + 2?",
        )

    assert result.error is not None
    assert result.tool_used is None


@pytest.mark.asyncio
async def test_tool_agent_db_persist_called_with_correct_args() -> None:
    """ToolAgent._persist_tool_result() is called with correct tool_name and task_id."""
    from agent import ToolAgent

    mock_provider = AsyncMock()
    mock_provider.complete_with_tools = AsyncMock(
        return_value=_tool_call_result("calculator", {"expression": "2 + 2"})
    )
    mock_provider.complete = AsyncMock(return_value=_llm_response("2 plus 2 is 4."))

    persist_calls: list[dict] = []

    async def capture_persist(**kwargs: Any) -> None:
        persist_calls.append(kwargs)

    with (
        patch("agent.get_llm_provider", return_value=mock_provider),
        patch("agent.ToolAgent._persist_tool_result", side_effect=capture_persist),
        patch("agent.ToolAgent._publish_event", new_callable=AsyncMock),
        patch(
            "agent.CalculatorTool.run",
            new_callable=AsyncMock,
            return_value={"result": 4, "expression": "2 + 2"},
        ),
    ):
        agent = ToolAgent(db_engine=None)
        await agent.run(
            task_id="task-persists-001",
            run_id="r1",
            user_id="u1",
            instruction="What is 2 + 2?",
        )

    assert len(persist_calls) == 1
    assert persist_calls[0]["task_id"] == "task-persists-001"
    assert persist_calls[0]["tool_name"] == "calculator"


@pytest.mark.asyncio
async def test_tool_agent_publishes_agent_start_and_end() -> None:
    """ToolAgent.run() publishes exactly 2 events: agent_start and agent_end."""
    from agent import ToolAgent

    mock_provider = AsyncMock()
    mock_provider.complete_with_tools = AsyncMock(
        return_value=_tool_call_result("calculator", {"expression": "1 + 1"})
    )
    mock_provider.complete = AsyncMock(return_value=_llm_response("1 plus 1 is 2."))

    events: list[str] = []

    async def capture_event(**kwargs: Any) -> None:
        events.append(kwargs["event_type"])

    with (
        patch("agent.get_llm_provider", return_value=mock_provider),
        patch("agent.ToolAgent._persist_tool_result", new_callable=AsyncMock),
        patch("agent.ToolAgent._publish_event", side_effect=capture_event),
        patch("agent.CalculatorTool.run", new_callable=AsyncMock, return_value={"result": 2}),
    ):
        agent = ToolAgent(db_engine=None)
        await agent.run(task_id="t1", run_id="r1", user_id="u1", instruction="1 + 1?")

    assert events[0] == "agent_start"
    assert events[-1] == "agent_end"


@pytest.mark.asyncio
async def test_tool_agent_unknown_tool_returns_error_in_output() -> None:
    """ToolAgent._execute_tool() returns error dict for unknown tool name."""
    from agent import ToolAgent

    agent = ToolAgent(db_engine=None)
    result = await agent._execute_tool("nonexistent_tool", {})
    assert "error" in result
    assert "Unknown tool" in result["error"]


# ── main.py endpoint tests ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_run_endpoint_missing_instruction_returns_error() -> None:
    """POST /run with empty input.instruction returns error."""
    from fastapi.testclient import TestClient
    from main import app

    with TestClient(app) as client:
        response = client.post(
            "/run",
            json={
                "run_id": "r1",
                "task_id": "t1",
                "user_id": "u1",
                "task_type": "tool",
                "input": {},
                "attempt": 1,
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert data["error"] == "input.instruction is required"
    assert data["output"] is None


@pytest.mark.asyncio
async def test_tools_endpoint_returns_three_tools() -> None:
    """GET /tools returns list of 3 tool definitions."""
    from fastapi.testclient import TestClient
    from main import app

    with TestClient(app) as client:
        response = client.get("/tools")

    assert response.status_code == 200
    tools = response.json()
    assert len(tools) == 3
    names = {t["name"] for t in tools}
    assert names == {"calculator", "get_weather", "wikipedia_search"}


@pytest.mark.asyncio
async def test_healthz_returns_ok() -> None:
    """GET /healthz returns 200 with status ok."""
    from fastapi.testclient import TestClient
    from main import app

    with TestClient(app) as client:
        response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
