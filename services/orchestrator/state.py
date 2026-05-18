# services/orchestrator/state.py
"""
OrchestratorState and related TypedDicts for the NEXUS LangGraph orchestration graph.

OrchestratorState is the single mutable object threaded through every graph node.
All node functions accept and return this type.
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
    """A single planned task produced by the decompose_query node."""

    task_id: str              # UUID string assigned at plan time
    agent_type: AgentType     # Which agent handles this task
    description: str          # Human-readable description of what the agent should do
    depends_on: list[str]     # task_ids this task waits for before executing


class TaskResult(TypedDict):
    """The output of a completed agent task, recorded by record_result."""

    task_id: str
    agent_type: AgentType
    output: str               # Serialised agent output (text or JSON string)
    error: str | None         # Non-None if the task failed
    duration_ms: int


class OrchestratorState(TypedDict):
    """
    Complete mutable state object for one orchestration run.

    Passed into every LangGraph node. Nodes return a partial dict
    with only the keys they modified — LangGraph merges via reducer.
    """

    # Inputs (set at graph entry)
    run_id: str
    user_id: str
    query: str

    # Planning (set by decompose_query)
    plan: list[TaskPlan]

    # Execution tracking (updated by dispatch_next_task / record_result)
    dispatched_task_ids: list[str]
    task_results: list[TaskResult]

    # Synthesis (set by synthesize_output)
    final_output: str

    # Lifecycle
    status: RunStatus
    error: str | None

    # Observability
    total_prompt_tokens: int
    total_completion_tokens: int