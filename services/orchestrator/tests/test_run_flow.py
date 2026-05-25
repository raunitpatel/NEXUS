"""
Integration test for the full NEXUS orchestrator graph with mocked agent services.

Runs graph.ainvoke() with mocked LLM provider, mocked agent HTTP calls,
and mocked DB — verifies the complete node sequence without Docker containers.

Run:
    cd nexus
    python -m pytest tests/integration/test_run_flow.py -v --asyncio-mode=auto
"""

from __future__ import annotations

import json
import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from llm_provider import LLMResponse


def _make_initial_state(run_id: str | None = None) -> dict[str, Any]:
    """Return a minimal initial OrchestratorState."""
    return {
        "run_id": run_id or str(uuid.uuid4()),
        "user_id": str(uuid.uuid4()),
        "query": "What is the capital of France?",
        "task_plan": [],
        "completed_tasks": [],
        "pending_task": None,
        "task_result": None,
        "retry_count": 0,
        "final_output": None,
        "status": "running",
        "error": None,
        "input_tokens": 0,
        "output_tokens": 0,
        "metadata": {},
    }


@pytest.mark.asyncio
async def test_full_graph_run_with_mocked_agents() -> None:
    """
    End-to-end graph.ainvoke() with one search task completes without exception.

    Mocks: LLM provider (decompose + synthesize), httpx agent call, DB engine, Kafka.
    Verifies: state reaches finalize_run with status=completed and final_output set.
    """
    # LLM responses
    decompose_json = json.dumps(
        {
            "tasks": [
                {"agent_type": "search", "description": "Find capital of France", "depends_on": []}
            ]
        }
    )
    synthesize_text = "The capital of France is Paris."

    mock_provider = AsyncMock()
    mock_provider.complete = AsyncMock(
        side_effect=[
            LLMResponse(content=decompose_json, prompt_tokens=100, completion_tokens=50),
            LLMResponse(content=synthesize_text, prompt_tokens=200, completion_tokens=30),
        ]
    )

    # Agent HTTP response
    mock_http_response = MagicMock()
    mock_http_response.json.return_value = {"output": {"answer": "Paris"}, "error": None}
    mock_http_response.raise_for_status = MagicMock()

    mock_http_client = AsyncMock()
    mock_http_client.__aenter__ = AsyncMock(return_value=mock_http_client)
    mock_http_client.__aexit__ = AsyncMock(return_value=False)
    mock_http_client.post = AsyncMock(return_value=mock_http_response)

    # DB session
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_db_engine = MagicMock()

    with (
        patch("nodes.decompose_query.get_llm_provider", return_value=mock_provider),
        patch("nodes.synthesize_output.get_llm_provider", return_value=mock_provider),
        patch("nodes.decompose_query._publish_thought_event", new_callable=AsyncMock),
        patch("nodes.synthesize_output._publish_llm_response_event", new_callable=AsyncMock),
        patch("nodes.finalize_run._publish_run_event", new_callable=AsyncMock),
        patch("nodes.dispatch_next_task.httpx.AsyncClient", return_value=mock_http_client),
        patch("nodes.dispatch_next_task.task_exists", new_callable=AsyncMock, return_value=True),
        patch("nodes.decompose_query.insert_task_plan", new_callable=AsyncMock),
        patch("nodes.record_result.get_db_engine", return_value=mock_db_engine),
        patch("nodes.finalize_run.get_db_engine", return_value=mock_db_engine),
        patch(
            "nodes.record_result.async_sessionmaker",
            return_value=MagicMock(return_value=mock_session),
        ),
        patch(
            "nodes.finalize_run.async_sessionmaker",
            return_value=MagicMock(return_value=mock_session),
        ),
    ):
        from graph import build_graph

        graph = build_graph()
        final_state = await graph.ainvoke(_make_initial_state())

    assert final_state["status"] == "completed"
    assert final_state["final_output"] == synthesize_text
    assert len(final_state["completed_tasks"]) == 1
    assert final_state["completed_tasks"][0]["task_id"] is not None


@pytest.mark.asyncio
async def test_graph_run_agent_timeout_exhausts_retries() -> None:
    """
    Graph run where agent HTTP always times out exhausts retries and finalizes as failed.
    """
    import httpx

    decompose_json = json.dumps(
        {"tasks": [{"agent_type": "search", "description": "Find something", "depends_on": []}]}
    )

    mock_provider = AsyncMock()
    mock_provider.complete = AsyncMock(
        return_value=LLMResponse(content=decompose_json, prompt_tokens=100, completion_tokens=50)
    )

    mock_http_client = AsyncMock()
    mock_http_client.__aenter__ = AsyncMock(return_value=mock_http_client)
    mock_http_client.__aexit__ = AsyncMock(return_value=False)
    mock_http_client.post = AsyncMock(side_effect=httpx.TimeoutException("timeout"))

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("nodes.decompose_query.get_llm_provider", return_value=mock_provider),
        patch("nodes.decompose_query._publish_thought_event", new_callable=AsyncMock),
        patch("nodes.finalize_run._publish_run_event", new_callable=AsyncMock),
        patch("nodes.dispatch_next_task.httpx.AsyncClient", return_value=mock_http_client),
        patch("nodes.decompose_query.insert_task_plan", new_callable=AsyncMock),
        patch("nodes.record_result.get_db_engine", return_value=None),
        patch("nodes.finalize_run.get_db_engine", return_value=None),
    ):
        from graph import build_graph

        graph = build_graph()
        final_state = await graph.ainvoke(_make_initial_state())

    assert final_state["status"] == "failed"
    assert final_state["retry_count"] >= 3
