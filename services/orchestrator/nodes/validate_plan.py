"""
validate_plan node — checks the task plan is non-empty and all agent_type values are valid.

Stub implementation returns state unchanged.
Real implementation in AGNT-008 validates:
  - task_plan is non-empty
  - all agent_type values match agents.type constraint
  - no circular depends_on references
"""

import structlog

from state import OrchestratorState

logger = structlog.get_logger(__name__)


async def validate_plan(state: OrchestratorState) -> OrchestratorState:
    """Validate that the task plan produced by decompose_query is executable.

    Args:
        state: Current OrchestratorState with task_plan populated.

    Returns:
        Updated state. Sets error if plan is invalid. Stub returns unchanged.
    """
    logger.info("node.validate_plan.stub", run_id=state["run_id"])
    # --- AGNT-008: validation logic replaces this stub ---
    return state