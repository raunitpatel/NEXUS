"""

Verifies active_runs and orchestrator_runs_total are incremented/decremented
correctly in _run_graph(). All Prometheus metric calls are mocked.

Run:
    docker exec nexus-orchestrator python -m pytest tests/test_metrics.py -v --asyncio-mode=auto
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_run_graph_increments_active_runs_on_start() -> None:
    """active_runs.inc() is called when _run_graph starts."""
    mock_active_runs = MagicMock()
    mock_orchestrator_runs = MagicMock()

    mock_graph = AsyncMock()
    mock_graph.ainvoke = AsyncMock()

    with (
        patch("main.active_runs", mock_active_runs),
        patch("main.orchestrator_runs_total", mock_orchestrator_runs),
    ):
        from main import _run_graph

        await _run_graph(mock_graph, {"run_id": "r1"}, "r1")

    mock_active_runs.labels(service="orchestrator").inc.assert_called_once()


@pytest.mark.asyncio
async def test_run_graph_decrements_active_runs_on_completion() -> None:
    """active_runs.dec() is called in finally block regardless of success."""
    mock_active_runs = MagicMock()
    mock_orchestrator_runs = MagicMock()

    mock_graph = AsyncMock()
    mock_graph.ainvoke = AsyncMock()

    with (
        patch("main.active_runs", mock_active_runs),
        patch("main.orchestrator_runs_total", mock_orchestrator_runs),
    ):
        from main import _run_graph

        await _run_graph(mock_graph, {"run_id": "r1"}, "r1")

    mock_active_runs.labels(service="orchestrator").dec.assert_called_once()


@pytest.mark.asyncio
async def test_run_graph_decrements_active_runs_on_exception() -> None:
    """active_runs.dec() is called even when graph.ainvoke raises."""
    mock_active_runs = MagicMock()
    mock_orchestrator_runs = MagicMock()

    mock_graph = AsyncMock()
    mock_graph.ainvoke = AsyncMock(side_effect=RuntimeError("graph failed"))

    with (
        patch("main.active_runs", mock_active_runs),
        patch("main.orchestrator_runs_total", mock_orchestrator_runs),
    ):
        from main import _run_graph

        await _run_graph(mock_graph, {"run_id": "r1"}, "r1")

    mock_active_runs.labels(service="orchestrator").dec.assert_called_once()
    mock_orchestrator_runs.labels(status="failed").inc.assert_called_once()
