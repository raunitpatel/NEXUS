# services/orchestrator/nodes/synthesize_output.py
"""
LangGraph node: synthesize_output

Receives all completed task results from OrchestratorState and calls the
configured LLMProvider to produce a final natural-language answer for the user.

Publishes an llm_response event to nexus.events so the SSE emitter can deliver
the final answer to the frontend before finalize_run writes it to the DB.
"""

from __future__ import annotations
 
import json
from typing import Any
 
import structlog
 
from llm_provider import LLMProviderError, get_llm_provider
from nodes.decompose_query import OrchestratorError
from state import OrchestratorState, TaskResult
 
logger = structlog.get_logger(__name__)
 
# System prompt
 
_SYNTHESIZE_SYSTEM_PROMPT = """\
You are the synthesis component of NEXUS, an AI agent orchestration platform.
You have received the results of one or more specialized AI agents that worked
on a user's query. Your job is to produce a single, coherent, accurate, and
well-structured response for the user.
 
Instructions:
- Integrate all relevant information from the task results below.
- Be concise but complete. Do not pad with filler.
- If a task failed, acknowledge the gap gracefully rather than fabricating data.
- Respond in plain prose unless the user query specifically asks for code, lists, \
or tables.
- Do NOT reference "Task 1", "Task 2" or internal agent names in your response.
"""
 
 
# Node function
 
async def synthesize_output(state: OrchestratorState) -> dict[str, Any]:
    """
    LangGraph node that synthesizes all task results into a final user-facing answer.
 
    Formats completed_tasks as a context block, calls LLMProvider, sets
    final_output, updates token counters, and publishes an llm_response Kafka event.
 
    Args:
        state: Current OrchestratorState. Reads: run_id, query, completed_tasks,
               input_tokens, output_tokens.
 
    Returns:
        Partial state dict with keys: final_output, input_tokens, output_tokens.
 
    Raises:
        OrchestratorError: If the LLM provider fails or returns empty output.
    """
    run_id = state["run_id"]
    query = state["query"]
    # FIX C4: read "completed_tasks" not "task_results"
    completed_tasks: list[TaskResult] = state.get("completed_tasks", [])
 
    logger.info(
        "synthesize_output.start",
        run_id=run_id,
        result_count=len(completed_tasks),
    )
 
    context_block = _format_task_results(completed_tasks)
 
    user_message = (
        f"Original user query:\n{query}\n\n"
        f"Agent task results:\n{context_block}\n\n"
        "Please synthesize the above into a final answer for the user."
    )
 
    provider = get_llm_provider()
 
    try:
        llm_response = await provider.complete(
            system=_SYNTHESIZE_SYSTEM_PROMPT,
            user=user_message,
            json_mode=False,
        )
    except LLMProviderError as exc:
        logger.error("synthesize_output.provider_error", run_id=run_id, error=str(exc))
        raise OrchestratorError(f"LLM provider failed during synthesis: {exc}") from exc
 
    final_output = llm_response.content.strip()
 
    if not final_output:
        raise OrchestratorError("LLM returned empty final_output during synthesis.")
 
    logger.info(
        "synthesize_output.success",
        run_id=run_id,
        output_length=len(final_output),
        prompt_tokens=llm_response.prompt_tokens,
        completion_tokens=llm_response.completion_tokens,
    )
 
    await _publish_llm_response_event(run_id=run_id, final_output=final_output)
 
    # FIX C3: token keys are "input_tokens"/"output_tokens"
    return {
        "final_output": final_output,
        "input_tokens": (state.get("input_tokens") or 0) + (llm_response.prompt_tokens or 0),
        "output_tokens": (state.get("output_tokens") or 0) + (llm_response.completion_tokens or 0),
    }
 
 
# Helpers
 
def _format_task_results(completed_tasks: list[TaskResult]) -> str:
    """
    Format completed task results into a numbered context block for the LLM.
 
    Output dict is JSON-serialized so the LLM sees structured data not a
    raw Python dict repr.
 
    Args:
        completed_tasks: All completed (and failed) task results from state.
 
    Returns:
        Multi-line string with each result on its own labelled block.
    """
    if not completed_tasks:
        return "(No task results available — all tasks may have been skipped or failed.)"
 
    lines: list[str] = []
    for i, result in enumerate(completed_tasks, start=1):
        status = "FAILED" if result.get("error") else "SUCCESS"
        lines.append(
            f"--- Result {i} [{result['agent_type'].upper()} | {status}] ---"
        )
        if result.get("error"):
            lines.append(f"Error: {result['error']}")
        else:
            output = result.get("output", {})
            # Serialize dict to JSON string so LLM sees clean structured data
            lines.append(json.dumps(output, indent=2) if output else "(empty output)")
        lines.append("")
 
    return "\n".join(lines)
 
 
async def _publish_llm_response_event(run_id: str, final_output: str) -> None:
    """
    Publish an llm_response event to nexus.events Kafka topic.
 
    Failures are logged and swallowed — must not abort a completed run.
 
    Args:
        run_id: The orchestration run ID.
        final_output: The synthesized answer to include in the payload.
    """
    from config import settings
    from shared.kafka_client import KafkaProducerFactory
    from shared.kafka_schemas import EventMessage
 
    try:
        producer = await KafkaProducerFactory.get_producer(
            bootstrap_servers=settings.kafka_bootstrap_servers
        )
        event = EventMessage(
            run_id=run_id,
            event_type="llm_response",
            source="orchestrator.synthesize_output",
            payload={"content": final_output[:2000]},
        )
        await producer.send(
            settings.kafka_topic_events,
            value=event.model_dump_json().encode(),
        )
    except Exception as exc:
        logger.warning(
            "synthesize_output.kafka_publish_failed",
            run_id=run_id,
            error=str(exc),
        )
 