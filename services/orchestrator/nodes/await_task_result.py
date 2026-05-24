# services/orchestrator/nodes/await_task_result.py
"""
await_task_result node — normalises the agent HTTP response into a TaskResult.

In the MVP synchronous HTTP model, the agent response is already stored in
state["pending_task"]["_response"] by dispatch_next_task. This node reads
that response and constructs a normalised TaskResult TypedDict.

IMPORTANT: We preserve the FULL agent response in raw_response so that
finalize_run and SSE payloads can render rich execution traces. We never
discard nested payloads.

AGNT-013 upgrades this to consume from Kafka nexus.results with asyncio.wait_for.
"""

from __future__ import annotations

from typing import Any

import structlog

from state import OrchestratorState, TaskResult

logger = structlog.get_logger(__name__)


def _extract_normalized_output(response_data: dict[str, Any]) -> dict[str, Any]:
    """
    Extract and preserve the full agent output from the response.

    Handles multiple agent response shapes:
      - {"output": {...}, "error": null}          — standard shape
      - {"output": {"results": [...]}}             — search agent
      - {"output": {"code": "...", "result": ...}} — code agent
      - {"output": {"content": "..."}}             — memory agent
      - {"output": {"answer": "..."}}              — tool agent

    NEVER returns empty dict if the response has meaningful data.

    Args:
        response_data: Raw JSON response dict from the agent /run endpoint.

    Returns:
        Normalized output dict preserving all nested data.
    """
    # Get the raw output field
    raw_output = response_data.get("output")

    # If output is a non-empty dict, return it directly
    if isinstance(raw_output, dict) and raw_output:
        return raw_output

    # If output is a non-empty string, wrap it
    if isinstance(raw_output, str) and raw_output.strip():
        return {"content": raw_output}

    # If output is a list with items, wrap it
    if isinstance(raw_output, list) and raw_output:
        return {"results": raw_output}

    # If output is None/empty, try to find meaningful data in the top-level response
    for key in ("result", "content", "answer", "data", "synthesize", "run_output", "text"):
        val = response_data.get(key)
        if val is not None and val != "" and val != {} and val != []:
            return {key: val}

    # Return whatever came in as output, defaulting to empty dict only as last resort
    return raw_output if isinstance(raw_output, dict) else {}


def _extract_summary(response_data: Any) -> str | None:
    """
    Extract a short human-readable summary from arbitrary agent responses.
    Handles:
    - dicts
    - strings
    - arrays
    - nested payloads
    """

    if response_data is None:
        return None

    # Direct string response
    if isinstance(response_data, str):
        cleaned = response_data.strip()
        return cleaned if cleaned else None

    # Lists
    if isinstance(response_data, list):
        for item in response_data:
            result = _extract_summary(item)
            if result:
                return result
        return None

    # Dicts
    if isinstance(response_data, dict):
        priority_keys = [
            "summary",
            "content",
            "answer",
            "result",
            "response",
            "message",
            "text",
            "stdout",
            "stderr",
        ]

        for key in priority_keys:
            value = response_data.get(key)
            if isinstance(value, str) and value.strip():
                return value

        # recurse nested values
        for value in response_data.values():
            result = _extract_summary(value)
            if result:
                return result

    return None

async def await_task_result(state: OrchestratorState) -> dict[str, Any]:
    """
    Normalise the agent response stored in pending_task into a TaskResult.

    Reads _response, _elapsed_ms, and _attempt from pending_task.
    Sets state["task_result"] with the normalised output, preserving the
    full raw_response for downstream consumers (finalize_run, SSE emitter).

    Args:
        state: Current OrchestratorState with pending_task populated by
               dispatch_next_task.

    Returns:
        Partial state dict with task_result set (and optionally error set).
    """
    run_id = state["run_id"]
    pending_task = state.get("pending_task")

    if not pending_task:
        msg = "await_task_result called but pending_task is None."
        logger.error("node.await_task_result.no_pending_task", run_id=run_id)
        return {"error": msg}

    task_id: str = pending_task["task_id"]
    agent_type: str = pending_task["agent_type"]
    response_data: dict[str, Any] = pending_task.get("_response", {})
    elapsed_ms: int = pending_task.get("_elapsed_ms", 0)
    attempt: int = pending_task.get("_attempt", 1)

    # Agent services return {"output": {...}, "error": null | "error message"}
    agent_error: str | None = response_data.get("error")

    # --- AGNT-FIX: preserve full output, never discard ---
    normalized_output = _extract_normalized_output(response_data)
    summary = _extract_summary(response_data)

    # Build rich task result preserving full response
    task_result: dict[str, Any] = {
        "task_id": task_id,
        "agent_type": agent_type,
        "output": normalized_output,
        "raw_response": response_data,       # full response for debugging/traces
        "summary": summary,                  # human-readable summary
        "error": agent_error,
        "duration_ms": elapsed_ms,
        "attempt": attempt,
    }

    if agent_error:
        logger.warning(
            "node.await_task_result.agent_error",
            run_id=run_id,
            task_id=task_id,
            agent_type=agent_type,
            error=agent_error,
        )
        return {"task_result": task_result, "error": agent_error}

    logger.info(
        "node.await_task_result.success",
        run_id=run_id,
        task_id=task_id,
        agent_type=agent_type,
        duration_ms=elapsed_ms,
        has_output=bool(normalized_output),
        output_keys=list(normalized_output.keys()) if isinstance(normalized_output, dict) else [],
    )

    return {"task_result": task_result}