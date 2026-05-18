"""OrchestratorState TypedDict and supporting data structures.

OrchestratorState is the single mutable object that flows through every
LangGraph node in graph.py. All node functions accept and return this type.

Keeping state as a TypedDict (rather than a Pydantic model) is intentional:
LangGraph requires dict-compatible state, and TypedDict provides mypy type
safety without Pydantic validation overhead on every state transition.

Status values for the `status` field must match the runs.status CHECK constraint
in db/schema.sql exactly: 'pending', 'running', 'completed', 'failed', 'cancelled'.

Agent type values for TaskPlan.agent_type must match agents.type CHECK constraint
in db/schema.sql exactly: 'search', 'code', 'memory', 'tool', 'orchestrator'.

Task type values for TaskPlan.task_type must match tasks.type CHECK constraint
in db/schema.sql exactly: 'search', 'code', 'memory_read', 'memory_write', 'tool', 'synthesize'.
"""
from typing import Any, TypedDict


class TaskPlan (TypedDict):
    """
    A single agent task produced by the decompose_query node.

    Attributes:
        task_id: UUID string for this task, written to the tasks table.
        agent_type: One of 'search', 'code', 'memory', 'tool' — matches agents.type constraint.
        task_type: One of 'search', 'code', 'memory_read', 'memory_write', 'tool', 'synthesize'
                — matches tasks.type constraint in db/schema.sql.
        agent_url: Internal Docker service URL for the target agent.
        input: Arbitrary JSON-serializable dict sent as the task payload.
        depends_on: List of task_ids that must complete before this task dispatches.
    """
    task_id: str
    agent_type: str
    task_type: str
    agent_url: str
    input: dict[str, Any]
    depends_on: list[str]

class TaskResult(TypedDict):
    """T
    he result returned by an agent after completing a task.

    Attributes:
        task_id: UUID string matching the originating TaskPlan.
        agent_type: Which agent produced this result.
        output: Arbitrary JSON-serializable dict from the agent.
        error: Non-None string if the agent reported a failure.
        duration_ms: Wall-clock milliseconds the agent spent on this task.
        attempt: Which retry attempt produced this result (1-indexed).
    """
    task_id: str
    agent_type: str
    output: dict[str, Any]
    error: str | None
    duration_ms: int
    attempt: int

class OrchestratorState(TypedDict):
    """
    Single shared state object flowing through every LangGraph node.

    LangGraph merges partial dicts returned by nodes — any key not returned
    by a node retains its previous value. All keys except run_id, user_id,
    and query are therefore optional at graph entry.

    Token counter fields (input_tokens, output_tokens) are required by
    decompose_query and synthesize_output nodes which accumulate
    LLM token usage across the full orchestration run.

    Attributes:
        run_id: UUID string matching runs.id primary key.
        user_id: UUID string of the authenticated user.
        query: Raw user query string from POST /orchestrate.
        task_plan: Ordered list of TaskPlan dicts from decompose_query.
        completed_tasks: Accumulating list of TaskResult dicts from record_result.
        pending_task: The single TaskPlan currently being dispatched.
        task_result: The TaskResult for the most recently awaited task.
        retry_count: How many times handle_error has been invoked for the current task.
        final_output: Synthesized answer string written to runs.output.
        status: Current run status — must be one of: pending, running, completed, failed, cancelled.
        error: Error message if any node has failed.
        input_tokens: Cumulative LLM input tokens consumed across all nodes (AGNT-008).
        output_tokens: Cumulative LLM output tokens produced across all nodes (AGNT-008).
        metadata: Arbitrary extra context: latency stats, model name, Kafka offsets, etc.
    """
    run_id: str
    user_id: str
    query: str
    task_plan: list[TaskPlan]
    completed_tasks: list[TaskResult]
    pending_task: TaskPlan | None
    task_result: TaskResult | None
    retry_count: int
    final_output: str | None
    status: str
    error: str | None
    input_tokens: int
    output_tokens: int
    metadata: dict[str, Any]
