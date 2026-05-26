from __future__ import annotations

from typing import Annotated, Any

import httpx
import structlog
from dependencies import get_current_user
from fastapi import APIRouter, Depends, HTTPException, Query, status

logger = structlog.get_logger(__name__)

router = APIRouter()

_ORCHESTRATOR_URL = "http://nexus-orchestrator:8001"


# ──────────────────────────────────────────────────────────────────────────────
# GET /api/v1/memory/search
# ──────────────────────────────────────────────────────────────────────────────


@router.get(
    "/search",
    summary="Semantic search over user memory",
)
async def search_memory(
    current_user: Annotated[dict[str, str], Depends(get_current_user)],
    q: str = Query(..., min_length=1, max_length=500),
    limit: int = Query(default=10, ge=1, le=50),
    similarity_threshold: float = Query(default=0.35, ge=0.0, le=1.0),
) -> dict[str, Any]:
    """
    Proxy semantic memory search to orchestrator.
    """

    user_id = current_user["user_id"]

    logger.info(
        "memory.search.proxy",
        user_id=user_id,
        query=q[:80],
    )

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{_ORCHESTRATOR_URL}/memory/search",
                params={
                    "q": q,
                    "limit": limit,
                    "similarity_threshold": similarity_threshold,
                },
                headers={
                    "x-user-id": user_id,
                },
            )

    except httpx.ConnectError:
        logger.error(
            "memory.search.orchestrator_unreachable",
            user_id=user_id,
        )

        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Orchestrator is unreachable",
        )

    except httpx.TimeoutException:
        logger.error(
            "memory.search.orchestrator_timeout",
            user_id=user_id,
        )

        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Orchestrator timed out",
        )

    if response.status_code != 200:
        logger.error(
            "memory.search.orchestrator_error",
            user_id=user_id,
            status=response.status_code,
            body=response.text,
        )

        raise HTTPException(
            status_code=response.status_code,
            detail=response.text,
        )

    return response.json()


# ──────────────────────────────────────────────────────────────────────────────
# GET /api/v1/memory
# ──────────────────────────────────────────────────────────────────────────────


@router.get(
    "",
    summary="List recent user memories",
)
async def list_memory(
    current_user: Annotated[dict[str, str], Depends(get_current_user)],
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> list[dict[str, Any]]:
    """
    Proxy memory listing to orchestrator.
    """

    user_id = current_user["user_id"]

    logger.info(
        "memory.list.proxy",
        user_id=user_id,
    )

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{_ORCHESTRATOR_URL}/memory",
                params={
                    "limit": limit,
                    "offset": offset,
                },
                headers={
                    "x-user-id": user_id,
                },
            )

    except httpx.ConnectError:
        logger.error(
            "memory.list.orchestrator_unreachable",
            user_id=user_id,
        )

        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Orchestrator is unreachable",
        )

    except httpx.TimeoutException:
        logger.error(
            "memory.list.orchestrator_timeout",
            user_id=user_id,
        )

        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Orchestrator timed out",
        )

    if response.status_code != 200:
        logger.error(
            "memory.list.orchestrator_error",
            user_id=user_id,
            status=response.status_code,
            body=response.text,
        )

        raise HTTPException(
            status_code=response.status_code,
            detail=response.text,
        )

    return response.json()