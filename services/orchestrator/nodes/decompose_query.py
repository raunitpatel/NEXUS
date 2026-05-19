# services/orchestrator/nodes/decompose_query.py
"""
LangGraph node: decompose_query

Receives the raw user query from OrchestratorState and calls the configured
LLMProvider to produce a structured task plan (list[TaskPlan]).

The plan is validated by Pydantic before being written to state.
A Kafka event is published to nexus.events so the SSE emitter can stream
the planning thought to the frontend in real time.
"""
from __future__ import annotations

import json
import uuid
from typing import Any

import structlog
from pydantic import BaseModel, ValidationError, field_validator

from llm_provider import LLMProviderError, get_llm_provider
from state import AgentType, OrchestratorState, TaskPlan
 
logger = structlog.get_logger(__name__)
 
# Pydantic model for LLM response validation
 
_VALID_AGENT_TYPES: set[str] = {
    "search",
    "code",
    "memory_read",
    "memory_write",
    "tool",
}
 
 
class _TaskPlanItem(BaseModel):
    """Pydantic model used to validate a single task returned by the LLM."""
 
    agent_type: str
    description: str
    depends_on: list[str] = []
 
    @field_validator("agent_type")
    @classmethod
    def validate_agent_type(cls, v: str) -> str:
        """Ensure agent_type is one of the allowed NEXUS values."""
        if v not in _VALID_AGENT_TYPES:
            raise ValueError(
                f"Invalid agent_type '{v}'. Must be one of: {sorted(_VALID_AGENT_TYPES)}"
            )
        return v
 
 
class _DecomposeResponse(BaseModel):
    """Root wrapper expected from the LLM — either a bare list or {tasks: [...]}."""
 
    tasks: list[_TaskPlanItem]
 
 
# System prompt
 
_DECOMPOSE_SYSTEM_PROMPT = """\
You are the planning component of NEXUS, an AI agent orchestration platform.
Your job is to decompose a user query into a structured list of agent tasks.
 
Available agent types and their capabilities:
- search: Web search, document retrieval, fact-finding
- code: Write, execute, and debug Python code
- memory_read: Retrieve relevant context from past agent runs via semantic search
- memory_write: Store important information into the vector memory store
- tool: Calculator, weather lookup, Wikipedia queries

Rules:
1. Return ONLY valid JSON. No prose, no markdown, no code fences.
2. The JSON must be an object with a single key "tasks" containing an array.
3. Each task object must have: "agent_type" (string), "description" (string), \
"depends_on" (array of task indices as strings, empty if no dependency).
4. Minimum 1 task, maximum 6 tasks.
5. Task indices in depends_on refer to the position (0-based) of tasks in the array.

Example output:
{
    "tasks": [
        {
            "agent_type": "memory_read",
            "description": "Retrieve previous stored context about Kafka orchestration systems",
            "depends_on": []
        },
        {
            "agent_type": "search",
            "description": "Find latest best practices for Kafka orchestration",
            "depends_on": []
        },
        {
            "agent_type": "code",
            "description": "Generate an architecture diagram and implementation example combining prior context and latest practices",
            "depends_on": ["0", "1"]
        }
    ]
}
"""
 
 
# Node function
 
async def decompose_query(state: OrchestratorState) -> dict[str, Any]:
    """
    LangGraph node that decomposes the user query into a list[TaskPlan].
 
    Calls the configured LLMProvider in JSON mode, validates the response with
    Pydantic, assigns deterministic task IDs, resolves agent URLs, and publishes
    a Kafka thought event.
 
    Args:
        state: Current OrchestratorState. Reads: run_id, user_id, query,
            input_tokens, output_tokens.
 
    Returns:
        Partial state dict with keys: task_plan, input_tokens, output_tokens.
 
    Raises:
        OrchestratorError: If the LLM returns an invalid plan or provider fails.
    """
    run_id = state["run_id"]
    query = state["query"]
 
    logger.info("decompose_query.start", run_id=run_id, query=query[:100])
 
    provider = get_llm_provider()
 
    try:
        llm_response = await provider.complete(
            system=_DECOMPOSE_SYSTEM_PROMPT,
            user=f"Decompose this query into agent tasks:\n\n{query}",
            json_mode=True,
        )
    except LLMProviderError as exc:
        logger.error("decompose_query.provider_error", run_id=run_id, error=str(exc))
        raise OrchestratorError(f"LLM provider failed during decompose: {exc}") from exc
 
    # Parse and validate LLM JSON output
    try:
        raw = json.loads(llm_response.content)
        if isinstance(raw, list):
            raw = {"tasks": raw}
        decompose_response = _DecomposeResponse.model_validate(raw)
    except (json.JSONDecodeError, ValidationError) as exc:
        logger.error(
            "decompose_query.invalid_response",
            run_id=run_id,
            raw_content=llm_response.content[:500],
            error=str(exc),
        )
        raise OrchestratorError(
            f"LLM returned invalid task plan JSON: {exc}"
        ) from exc
 
    tasks = decompose_response.tasks
 
    if not (1 <= len(tasks) <= 6):
        raise OrchestratorError(
            f"Plan must contain 1–6 tasks, got {len(tasks)}."
        )
 
    # Lazy import to avoid module-level circular dependency:
    # decompose_query → dispatch_next_task → (config, state) — all fine at runtime
    # but importing at module level would create an import-time cycle because
    # dispatch_next_task also imports from decompose_query (OrchestratorError).
    # The lazy import here executes after all modules are loaded. ✓
    from nodes.dispatch_next_task import _resolve_agent_url
 
    plan: list[TaskPlan] = []
    for task in tasks:
        try:
            agent_url = _resolve_agent_url(task.agent_type)
        except ValueError:
            agent_url = ""  # validate_plan will catch unknown agent types
 
        plan.append(
            TaskPlan(
                task_id=str(uuid.uuid4()),
                agent_type=task.agent_type,      # type: ignore[arg-type]
                task_type=task.agent_type,        # type: ignore[arg-type]
                agent_url=agent_url,
                input={"query": query, "description": task.description},
                depends_on=task.depends_on,
            )
        )
 
    logger.info(
        "decompose_query.success",
        run_id=run_id,
        task_count=len(plan),
        agent_types=[t["agent_type"] for t in plan],
    )
 
    await _publish_thought_event(
        run_id=run_id,
        content=(
            f"Decomposed query into {len(plan)} task(s): "
            + ", ".join(t["agent_type"] for t in plan)
        ),
    )
 
    # FIX C2: return key is "task_plan" not "plan"
    # FIX C3: token keys are "input_tokens"/"output_tokens" not "total_prompt_tokens"
    return {
        "task_plan": plan,
        "input_tokens": (state.get("input_tokens") or 0) + (llm_response.prompt_tokens or 0),
        "output_tokens": (state.get("output_tokens") or 0) + (llm_response.completion_tokens or 0),
    }
 
 
# Helpers
 
async def _publish_thought_event(run_id: str, content: str) -> None:
    """
    Publish a thought event to the nexus.events Kafka topic.
 
    Failures are logged and swallowed — Kafka publish must not abort a run.
 
    Args:
        run_id: The orchestration run ID.
        content: Human-readable thought string.
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
            event_type="thought",
            source="orchestrator.decompose_query",
            payload={"content": content},
        )
        await producer.send(
            settings.kafka_topic_events,
            value=event.model_dump_json().encode(),
        )
    except Exception as exc:
        logger.warning(
            "decompose_query.kafka_publish_failed",
            run_id=run_id,
            error=str(exc),
        )
 
 
# Shared exception — imported by synthesize_output and other nodes
 
class OrchestratorError(Exception):
    """Raised by orchestrator nodes to signal a recoverable or fatal run failure."""
 