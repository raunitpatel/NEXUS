"""
decompose_query node — calls LLMProvider to break a user query into a list[TaskPlan].

Stub implementation returns state with empty task_plan and status='running'.
- OllamaProvider.complete(system_prompt, user_prompt) call
- Pydantic JSON parsing of the LLM response into list[TaskPlan]
- input_tokens / output_tokens accumulation on state
- Kafka event emission to nexus.events
"""

import structlog

from state import OrchestratorState

logger = structlog.get_logger(__name__)

async def decompose_query(state: OrchestratorState) -> OrchestratorState:
    """
    Break the user query into an ordered list of agent tasks via LLM.

    Args:
        state: Current OrchestratorState with run_id, user_id, query populated.

    Returns:
        Updated state with task_plan populated and status set to 'running'.
        Stub returns empty task_plan — AGNT-008 fills this with real LLM output.
    """
    logger.info("node.decompose_query.stub", run_id=state["run_id"])
    # --- AGNT-008: OllamaProvider call and Pydantic parsing replaces this stub ---
    return {
        **state,
        "task_plan": [],
        "status": "running",
    }

