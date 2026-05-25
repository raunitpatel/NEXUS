"""
LangGraph StateGraph definition for the NEXUS orchestrator.

build_graph() is the only public function. It wires all 8 nodes and 4 sets
of conditional edges, then compiles and returns the executable graph.

This file is topology-only. No business logic lives here. Node implementations
are in services/orchestrator/nodes/ and are replaced ticket by ticket (AGNT-008
through AGNT-014) without touching this file.

Edge map:
    START ──► decompose_query ──► validate_plan
    validate_plan ──► (error or empty plan)  ──► handle_error
    validate_plan ──► (valid plan)           ──► dispatch_next_task
    dispatch_next_task ──► (error)           ──► handle_error
    dispatch_next_task ──► (success)         ──► await_task_result
    await_task_result ──► (task error)       ──► handle_error
    await_task_result ──► (task ok)          ──► record_result
    record_result ──► (more tasks remain)    ──► dispatch_next_task
    record_result ──► (all tasks done)       ──► synthesize_output
    synthesize_output ──► finalize_run ──► END
    handle_error ──► (retries remain)        ──► dispatch_next_task
    handle_error ──► (retries exhausted)     ──► finalize_run

Diagram:
    START
    ↓
    decompose_query
    ↓
    validate_plan
    ├── invalid/error ──► handle_error
    └── valid ─────────► dispatch_next_task
                                ↓
                        await_task_result
                            ├── error ─► handle_error
                            └── success
                                ↓
                            record_result
                            ├── more tasks ─► dispatch_next_task
                            └── done ───────► synthesize_output
                                                    ↓
                                            finalize_run
                                                    ↓
                                                END
"""

from config import settings
from langgraph.graph import END, START, StateGraph
from nodes.await_task_result import await_task_result
from nodes.decompose_query import decompose_query
from nodes.dispatch_next_task import dispatch_next_task
from nodes.finalize_run import finalize_run
from nodes.handle_error import handle_error
from nodes.record_result import record_result
from nodes.synthesize_output import synthesize_output
from nodes.validate_plan import validate_plan
from state import OrchestratorState

# Conditional edge routing functions


def _route_after_validate(state: OrchestratorState) -> str:
    """
    Route to dispatch_next_task if plan is valid, otherwise handle_error.

    A plan is invalid if state has an error set OR task_plan is empty.

    Args:
        state: OrchestratorState after validate_plan executes.

    Returns:
        'dispatch_next_task' or 'handle_error'.
    """
    if state.get("error") or not state.get("task_plan"):
        return "handle_error"
    return "dispatch_next_task"


def _route_after_dispatch(state: OrchestratorState) -> str:
    """
    Route to handle_error if dispatch failed, otherwise await_task_result.

    dispatch_next_task sets state["error"] and does NOT set pending_task on
    HTTP timeout, connection failure, or unknown agent_type. Routing directly
    to await_task_result in that case causes an infinite loop (see audit C6).

    Args:
        state: OrchestratorState after dispatch_next_task executes.

    Returns:
        'handle_error' or 'await_task_result'.
    """
    if state.get("error"):
        return "handle_error"
    return "await_task_result"


def _route_after_await(state: OrchestratorState) -> str:
    """
    Route to handle_error if task failed, otherwise record_result.

    Args:
        state: OrchestratorState after await_task_result executes.

    Returns:
        'handle_error' or 'record_result'.
    """
    task_result = state.get("task_result")
    if task_result and task_result.get("error"):
        return "handle_error"
    return "record_result"


def _route_after_record(state: OrchestratorState) -> str:
    """
    Route to dispatch_next_task if more tasks remain, otherwise synthesize_output.

    Args:
        state: OrchestratorState after record_result executes.

    Returns:
        'dispatch_next_task' or 'synthesize_output'.
    """
    completed = len(state.get("completed_tasks", []))
    total = len(state.get("task_plan", []))
    if completed < total:
        return "dispatch_next_task"
    return "synthesize_output"


def _route_after_error(state: OrchestratorState) -> str:
    """
    Route to dispatch_next_task if retries remain, otherwise finalize_run.

    handle_error increments retry_count before this router is called,
    so retry_count == max_plan_retries means the last retry was just used.

    Args:
        state: OrchestratorState after handle_error executes.

    Returns:
        'dispatch_next_task' or 'finalize_run'.
    """
    if state.get("retry_count", 0) < settings.max_plan_retries:
        return "dispatch_next_task"
    return "finalize_run"


# Graph factory


def build_graph() -> object:
    """
    Construct and compile the NEXUS orchestrator LangGraph StateGraph.

    Called once at application startup inside the FastAPI lifespan context
    manager. The compiled graph is stored on app.state.graph and reused
    for every request — compilation is expensive and must not happen per-request.

    Returns:
        CompiledStateGraph — the executable LangGraph graph.
        Typed as object to avoid importing langgraph internals at call sites.
    """
    graph: StateGraph = StateGraph(OrchestratorState)

    # Register all 8 nodes
    graph.add_node("decompose_query", decompose_query)
    graph.add_node("validate_plan", validate_plan)
    graph.add_node("dispatch_next_task", dispatch_next_task)
    graph.add_node("await_task_result", await_task_result)
    graph.add_node("record_result", record_result)
    graph.add_node("synthesize_output", synthesize_output)
    graph.add_node("finalize_run", finalize_run)
    graph.add_node("handle_error", handle_error)

    # Fixed edges
    graph.add_edge(START, "decompose_query")
    graph.add_edge("decompose_query", "validate_plan")
    graph.add_edge("synthesize_output", "finalize_run")
    graph.add_edge("finalize_run", END)

    # Conditional edges
    graph.add_conditional_edges(
        "validate_plan",
        _route_after_validate,
        {
            "dispatch_next_task": "dispatch_next_task",
            "handle_error": "handle_error",
        },
    )
    graph.add_conditional_edges(
        "dispatch_next_task",
        _route_after_dispatch,
        {
            "handle_error": "handle_error",
            "await_task_result": "await_task_result",
        },
    )
    graph.add_conditional_edges(
        "await_task_result",
        _route_after_await,
        {
            "handle_error": "handle_error",
            "record_result": "record_result",
        },
    )
    graph.add_conditional_edges(
        "record_result",
        _route_after_record,
        {
            "dispatch_next_task": "dispatch_next_task",
            "synthesize_output": "synthesize_output",
        },
    )
    graph.add_conditional_edges(
        "handle_error",
        _route_after_error,
        {
            "dispatch_next_task": "dispatch_next_task",
            "finalize_run": "finalize_run",
        },
    )

    return graph.compile()
