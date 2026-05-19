# services/shared/kafka_schemas.py
"""
Pydantic v2 schemas for all Kafka message payloads exchanged between NEXUS services.

Every message produced to or consumed from a Kafka topic must be validated
against one of these schemas. Producers call .model_dump_json() to serialise.
Consumers call Model.model_validate_json() to deserialise.

Topics and their primary schemas:
    nexus.tasks   → TaskDispatchedMessage   (orchestrator → agents)
    nexus.results → TaskResultMessage       (agents → orchestrator)
    nexus.events  → EventMessage            (orchestrator/agents → SSE emitter)

All schemas include a schema_version field so consumers can handle
backwards-incompatible changes gracefully during rolling deploys.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field


# Shared types

AgentType = Literal[
    "search",
    "code",
    "memory_read",
    "memory_write",
    "tool",
]

TaskStatus = Literal[
    "pending",
    "running",
    "completed",
    "failed",
    "retrying",
]

EventType = Literal[
    "thought",
    "tool_call",
    "tool_result",
    "agent_start",
    "agent_end",
    "orchestrator_plan",
    "orchestrator_dispatch",
    "orchestrator_synthesize",
    "run_start",
    "run_complete",
    "run_error",
    "memory_read",
    "memory_write",
    "llm_response",
    "code_iteration"
]


# nexus.tasks — orchestrator → agents

class TaskDispatchedMessage(BaseModel):
    """
    Published to nexus.tasks when the orchestrator dispatches a task to an agent.

    Consumed by the target agent service's Kafka consumer loop.
    The agent_type field determines which Kafka partition the message lands on
    (4 partitions: one per agent type — see infra/kafka/create_topics.sh).

    Attributes:
        message_id: Unique ID for this Kafka message (for deduplication).
        schema_version: Incremented on breaking schema changes.
        run_id: UUID of the parent orchestration run.
        task_id: UUID of the task row in the tasks table.
        user_id: UUID of the user who initiated the run.
        agent_type: Which agent should process this task.
        task_type: Granular task classification (matches tasks.type DB constraint).
        input: Arbitrary JSON payload for the agent (query, code, search terms, etc.).
        attempt: Retry attempt number, 1-indexed.
        timeout_seconds: How long the agent has before the orchestrator times out.
        created_at: ISO 8601 UTC timestamp of dispatch.
    """

    message_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    schema_version: int = 1
    run_id: str
    task_id: str
    user_id: str
    agent_type: AgentType
    task_type: AgentType  # matches tasks.type CHECK constraint in db/schema.sql
    input: dict[str, Any] = Field(default_factory=dict)
    attempt: int = 1
    timeout_seconds: int = 30
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


# nexus.results — agents → orchestrator

class TaskResultMessage(BaseModel):
    """
    Published to nexus.results when an agent completes (or fails) a task.

    Consumed by the orchestrator's await_task_result node via Kafka consumer.
    The orchestrator correlates this message to the pending task using task_id.

    Attributes:
        message_id: Unique ID for this Kafka message.
        schema_version: Incremented on breaking schema changes.
        run_id: UUID of the parent orchestration run (for log correlation).
        task_id: UUID matching the TaskDispatchedMessage that triggered this work.
        agent_type: Which agent produced this result.
        status: Terminal status of the task.
        output: Serialised agent output — JSON string or plain text.
        error: Non-None error message if status is "failed".
        duration_ms: Wall-clock milliseconds the agent spent on this task.
        attempt: Which retry attempt produced this result.
        prompt_tokens: LLM input tokens consumed by the agent (0 if not applicable).
        completion_tokens: LLM output tokens consumed by the agent (0 if not applicable).
        created_at: ISO 8601 UTC timestamp of result publication.
    """

    message_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    schema_version: int = 1
    run_id: str
    task_id: str
    agent_type: AgentType
    status: TaskStatus
    output: str = ""          # serialised agent output; empty string on failure
    error: str | None = None
    duration_ms: int = 0
    attempt: int = 1
    prompt_tokens: int = 0
    completion_tokens: int = 0
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


# nexus.events — orchestrator/agents → SSE emitter / Gateway

class EventMessage(BaseModel):
    """
    Published to nexus.events to stream live thought traces to the frontend via SSE.

    Every significant step in a run emits an EventMessage — the Gateway's SSE
    router consumes these and pushes them to connected EventSource clients.

    This topic has 1 partition (strict ordering per run) with a 1-hour retention
    window — see infra/kafka/create_topics.sh.

    Attributes:
        event_id: Unique ID for this event (for frontend deduplication).
        schema_version: Incremented on breaking schema changes.
        run_id: UUID of the run this event belongs to.
        task_id: UUID of the specific task (None for run-level events).
        event_type: Semantic classification of the event.
        source: Dotted path identifying which node/service emitted this event.
                Examples: "orchestrator.decompose_query", "search_agent.web_search"
        payload: Arbitrary JSON data relevant to this event type.
                For "thought" events: {"content": "I need to search for..."}
                For "tool_call" events: {"tool": "web_search", "input": {...}}
                For "tool_result" events: {"tool": "web_search", "output": {...}}
                For "llm_response" events: {"content": "The answer is..."}
        created_at: ISO 8601 UTC timestamp — used by frontend to order events.
    """

    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    schema_version: int = 1
    run_id: str
    task_id: str | None = None
    event_type: EventType
    source: str
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


# Convenience re-exports

__all__ = [
    "AgentType",
    "TaskStatus",
    "EventType",
    "TaskDispatchedMessage",
    "TaskResultMessage",
    "EventMessage",
]