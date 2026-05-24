"""
Memory router for the API Gateway.

Proxies semantic memory search to the Memory Agent service.
All results are scoped to the authenticated user — users can only
search their own embedded run history.

Endpoints:
  GET  "/search"  — semantic similarity search over the user's embeddings
  GET  "/"        — list recent embeddings for the authenticated user

The Gateway does not call the Memory Agent's POST /run endpoint directly.
Instead it queries embeddings_metadata in Postgres for the list endpoint,
and proxies a memory_read task to the Memory Agent for semantic search.
This avoids the orchestrator overhead for simple direct memory queries
initiated from the frontend.
"""

from __future__ import annotations

from typing import Annotated, Any

import httpx
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from dependencies import get_current_user, get_db_session

logger = structlog.get_logger(__name__)
router = APIRouter()

# Internal Memory Agent URL — same pattern as orchestrator_url in config
_MEMORY_AGENT_URL = "http://nexus-memory-agent:8004"


# ── Response models ───────────────────────────────────────────────────────────


class MemorySearchResult(BaseModel):
    """
    A single semantic search result from the memory agent.

    Attributes:
        embedding_id: UUID of the embeddings_metadata row.
        run_id: UUID of the run that produced this embedding.
        content: The raw text that was embedded.
        similarity: Cosine similarity score (0.0–1.0, higher is more similar).
        model: Embedding model used (always all-MiniLM-L6-v2).
        created_at: ISO 8601 UTC timestamp string.
    """

    embedding_id: str
    run_id: str
    content: str
    similarity: float
    model: str
    created_at: str


class MemorySearchResponse(BaseModel):
    """
    Response from GET /api/v1/memory/search.

    Attributes:
        query: The search query string that was submitted.
        results: Ranked list of matching memory entries.
        from_cache: True if results were served from Redis cache.
        duration_ms: Time taken for the search operation.
    """

    query: str
    results: list[MemorySearchResult]
    from_cache: bool
    duration_ms: int


class EmbeddingEntry(BaseModel):
    """
    A single embedding entry returned by the list endpoint.

    Attributes:
        embedding_id: UUID of the embeddings_metadata row.
        run_id: UUID of the parent run.
        content: The embedded text (truncated to 300 chars).
        model: Embedding model name.
        created_at: ISO 8601 UTC timestamp string.
    """

    embedding_id: str
    run_id: str
    content: str
    model: str
    created_at: str


# ── GET /api/v1/memory/search ─────────────────────────────────────────────────


@router.get(
    "/search",
    response_model=MemorySearchResponse,
    summary="Semantic search over the authenticated user's memory",
)
async def search_memory(
    current_user: Annotated[dict[str, str], Depends(get_current_user)],
    q: str = Query(..., min_length=1, max_length=500, description="Semantic search query"),
    limit: int = Query(default=10, ge=1, le=50),
    similarity_threshold: float = Query(default=0.35, ge=0.0, le=1.0),
) -> MemorySearchResponse:
    """
    Perform a semantic similarity search over the user's embedded run history.

    Proxies a memory_read task directly to the Memory Agent service,
    bypassing the Orchestrator for speed. The Memory Agent enforces
    user scoping via the user_id field in its search cache key —
    two users with the same query get different results.

    Args:
        current_user: Injected by get_current_user.
        q: The natural language search query.
        limit: Maximum number of results to return.
        similarity_threshold: Minimum cosine similarity score (0.0–1.0).

    Returns:
        MemorySearchResponse with ranked results and timing metadata.

    Raises:
        HTTPException 503: If the Memory Agent is unreachable.
        HTTPException 502: If the Memory Agent returns an error.
    """
    user_id = current_user["user_id"]

    logger.info("memory.search", user_id=user_id, query=q[:80], limit=limit)

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{_MEMORY_AGENT_URL}/run",
                json={
                    "run_id": "gateway-direct",
                    "task_id": "gateway-direct",
                    "user_id": user_id,
                    "task_type": "memory_read",
                    "input": {
                        "query": q,
                        "limit": limit,
                        "similarity_threshold": similarity_threshold,
                    },
                    "attempt": 1,
                },
            )
    except httpx.ConnectError:
        logger.error("memory.search_agent_unreachable", user_id=user_id)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Memory agent is unreachable",
        )
    except httpx.TimeoutException:
        logger.error("memory.search_agent_timeout", user_id=user_id)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Memory agent timed out",
        )

    if response.status_code != 200:
        logger.error(
            "memory.search_agent_error",
            user_id=user_id,
            status=response.status_code,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Memory agent returned an error",
        )

    data = response.json()
    agent_error = data.get("error")

    if agent_error:
        logger.warning("memory.search_returned_error", user_id=user_id, error=agent_error)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=agent_error,
        )

    output: dict[str, Any] = data.get("output", {})
    raw_results: list[dict[str, Any]] = output.get("results", [])
    from_cache: bool = output.get("from_cache", False)
    duration_ms: int = output.get("duration_ms", 0)

    results = [
        MemorySearchResult(
            embedding_id=r.get("id", ""),
            run_id=r.get("run_id", ""),
            content=r.get("content", ""),
            similarity=float(r.get("similarity", 0.0)),
            model=r.get("model", "all-MiniLM-L6-v2"),
            created_at=r.get("created_at", ""),
        )
        for r in raw_results
    ]

    logger.info(
        "memory.search_complete",
        user_id=user_id,
        result_count=len(results),
        from_cache=from_cache,
    )

    return MemorySearchResponse(
        query=q,
        results=results,
        from_cache=from_cache,
        duration_ms=duration_ms,
    )


# ── GET /api/v1/memory ────────────────────────────────────────────────────────


@router.get(
    "",
    response_model=list[EmbeddingEntry],
    summary="List recent memory embeddings for the authenticated user",
)
async def list_memory(
    current_user: Annotated[dict[str, str], Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> list[EmbeddingEntry]:
    """
    Return recent embeddings stored from the authenticated user's runs.

    Queries embeddings_metadata joined to runs to enforce user ownership —
    a user can only see embeddings that came from their own runs.

    Args:
        current_user: Injected by get_current_user.
        db: Injected async SQLAlchemy session.
        limit: Max entries to return.
        offset: Pagination offset.

    Returns:
        List of EmbeddingEntry objects ordered by created_at DESC.
    """
    user_id = current_user["user_id"]

    result = await db.execute(
        text(
            """
            SELECT
                em.id::text          AS embedding_id,
                em.run_id::text      AS run_id,
                em.content,
                em.model,
                em.created_at::text  AS created_at
            FROM embeddings_metadata em
            JOIN runs r ON r.id = em.run_id
            WHERE r.user_id = :user_id
            ORDER BY em.created_at DESC
            LIMIT :limit OFFSET :offset
            """
        ),
        {"user_id": user_id, "limit": limit, "offset": offset},
    )
    rows = result.fetchall()

    logger.info("memory.list", user_id=user_id, count=len(rows))

    return [
        EmbeddingEntry(
            embedding_id=row.embedding_id,
            run_id=row.run_id,
            content=row.content[:300],
            model=row.model,
            created_at=row.created_at,
        )
        for row in rows
    ]