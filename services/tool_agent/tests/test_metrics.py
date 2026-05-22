# services/tool_agent/tests/test_metrics.py
"""
Unit tests for AGNT-017 metric instrumentation in ToolAgent.run().

Run:
    docker exec nexus-tool-agent python -m pytest tests/test_metrics.py -v --asyncio-mode=auto
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from llm_provider import LLMResponse, ToolCallResult


@pytest.mark.asyncio
async def test_tool_agent_records_duration_and_tokens_on_success() -> None:
    """agent_task_duration_seconds and llm_tokens_total incremented on successful run."""
    from agent import ToolAgent

    mock_provider = AsyncMock()
    mock_provider.complete_with_tools = AsyncMock(return_value=ToolCallResult(
        tool_name="calculator", tool_input={"expression": "1+1"},
        stop_reason="tool_use", prompt_tokens=100, completion_tokens=30,
    ))
    mock_provider.complete = AsyncMock(return_value=LLMResponse(
        content="2", prompt_tokens=50, completion_tokens=10,
    ))

    mock_duration = MagicMock()
    mock_tasks = MagicMock()
    mock_tokens = MagicMock()
    mock_requests = MagicMock()

    with (
        patch("agent.get_llm_provider", return_value=mock_provider),
        patch("agent.ToolAgent._persist_tool_result", new_callable=AsyncMock),
        patch("agent.ToolAgent._publish_event", new_callable=AsyncMock),
        patch("agent.CalculatorTool.run", new_callable=AsyncMock,
              return_value={"result": 2}),
        patch("agent.agent_task_duration_seconds", mock_duration),
        patch("agent.agent_tasks_total", mock_tasks),
        patch("agent.llm_tokens_total", mock_tokens),
        patch("agent.llm_requests_total", mock_requests),
    ):
        agent = ToolAgent(db_engine=None)
        await agent.run(task_id="t1", run_id="r1", user_id="u1", instruction="1+1?")

    mock_duration.labels(agent="tool", status="success").observe.assert_called_once()
    mock_tasks.labels(agent="tool", status="success").inc.assert_called_once()
    mock_tokens.labels.assert_called()