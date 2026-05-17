"""
Runs router stub for the API Gateway.

Returns an empty list for authenticated GET /api/v1/runs requests.

All endpoints here require a valid JWT (enforced by AuthMiddleware).
"""

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from dependencies import get_current_user

logger = structlog.get_logger(__name__)
router = APIRouter()

class RunSummary(BaseModel):
    """
    Minimal run representation returned in list views.
    """
    run_id: str
    status: str
    created_at: str

@router.get(
    "",
    response_model=list[RunSummary],
    summary="List all runs for the authenticated user",
)

async def list_runs(
    current_user: Annotated[dict[str, str], Depends(get_current_user)],
) -> list[RunSummary]:
    """
    Return all runs belonging to the authenticated user.

    Stub implementation returns an empty list. AGNT-007 adds DB queries,
    pagination, and status filters.

    Args:
        current_user: Injected by get_current_user dependency — dict with user_id and jti.

    Returns:
        Empty list (stub). Will return list[RunSummary] after AGNT-007.
    """
    logger.info("runs.list", user_id=current_user["user_id"])
    return []