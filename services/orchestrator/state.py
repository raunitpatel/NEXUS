# services/orchestrator/state.py
"""
OrchestratorState and related TypedDicts for the NEXUS LangGraph orchestration graph.

All field names are the canonical keys referenced by graph.py conditional edge
routers and all node functions. Any change here must be reflected in:
    - graph.py  (routing functions read state keys directly)
    - main.py   (initial_state dict must match exactly)
    - all nodes/ files
    - all tests/ _base_state() helpers

"""

from __future__ import annotations

from typing import Any, Literal

from typing_extensions import TypedDict

AgentType = Literal[
    "search",
    "code",
    "memory_read",
    "memory_write",
    "tool",
    "synthesize",
]

RunStatus = Literal["pending", "running", "completed", "failed", "cancelled"]


class TaskPlan(TypedDict):
    """
    A single planned task produced by the decompose_query node.

    Attributes:
        task_id:    Deterministic UUID string assigned at plan time.
        agent_type: Which agent class handles this task.
        task_type:  Granular task classification (matches tasks.type DB constraint).
        agent_url:  Internal Docker service URL resolved from config at plan time.
        input:      Arbitrary JSON payload forwarded to the agent /run endpoint.
        depends_on: List of 0-based string indices of tasks that must complete first.
    """

    task_id: str
    agent_type: AgentType
    task_type: AgentType
    agent_url: str
    input: dict[str, Any]
    depends_on: list[str]


class TaskResult(TypedDict):
    """
    The normalised output of a completed (or failed) agent task.

    Attributes:
        task_id:     UUID matching the TaskPlan that produced this result.
        agent_type:  Which agent produced this result.
        output:      Parsed JSON response dict from the agent /run endpoint.
        error:       Non-None error message if the task failed.
        duration_ms: Wall-clock milliseconds the agent spent on the task.
        attempt:     Which retry attempt (1-indexed) produced this result.
    """

    task_id: str
    agent_type: AgentType
    output: dict[str, Any]
    error: str | None
    duration_ms: int
    attempt: int
    raw_response: dict[str, Any]
    summary: str


class OrchestratorState(TypedDict):
    """
    Complete mutable state object for one orchestration run.

    Passed into every LangGraph node. Nodes return a partial dict with only
    the keys they modified — LangGraph merges via its default replace reducer
    (last-write-wins per key). Nodes that update list fields must return the
    full updated list, not just the new element.

    Attributes:
        run_id:          UUID of the runs table row (created by Gateway).
        user_id:         UUID of the authenticated user.
        query:           Raw user query string.
        task_plan:       Ordered list of TaskPlan dicts from decompose_query.
        completed_tasks: Accumulated TaskResult dicts from record_result.
        pending_task:    The TaskPlan currently being executed (set by dispatch,
                         cleared by record_result).
        task_result:     The most recent TaskResult (set by await_task_result,
                         cleared by record_result).
        final_output:    Synthesized answer string from synthesize_output.
        status:          Current run lifecycle status.
        error:           Most recent error message (set by failing nodes).
        retry_count:     Number of times handle_error has been invoked this run.
        input_tokens:    Accumulated LLM input tokens across all nodes.
        output_tokens:   Accumulated LLM output tokens across all nodes.
        metadata:        Arbitrary JSON metadata (latency, token counts at finish).
    """

    run_id: str
    user_id: str
    query: str

    task_plan: list[TaskPlan]
    completed_tasks: list[TaskResult]
    pending_task: TaskPlan | None
    task_result: TaskResult | None

    final_output: str | None

    status: RunStatus
    error: str | None
    retry_count: int

    input_tokens: int
    output_tokens: int
    metadata: dict[str, Any]
