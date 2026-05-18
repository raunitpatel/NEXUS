"""
synthesize_output node — calls LLMProvider to produce the final answer from all task results.

Stub implementation sets status='completed' and final_output=''.
AGNT-008 replaces the stub body with:
  - Building a synthesis prompt from completed_tasks outputs
  - OllamaProvider.complete(system_prompt, synthesis_prompt) call
  - Setting final_output on state
  - input_tokens / output_tokens accumulation on state
  - Kafka event emission to nexus.events
"""

import structlog

from state import OrchestratorState

logger = structlog.get_logger(__name__)


async def synthesize_output(state: OrchestratorState) -> OrchestratorState:
    """Synthesize all completed task outputs into a single coherent final answer.

    Args:
        state: Current OrchestratorState with all tasks in completed_tasks.

    Returns:
        Updated state with final_output set and status='completed'.
        Stub sets empty final_output — AGNT-008 fills with real LLM synthesis.
    """
    logger.info("node.synthesize_output.stub", run_id=state["run_id"])
    # --- AGNT-008: OllamaProvider synthesis call replaces this stub ---
    return {
        **state,
        "final_output": "",
        "status": "completed",
    }