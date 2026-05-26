from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, Header, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import text

from agents.memory_agent import MemoryAgent
from nodes.app_state import get_db_engine, get_db_pool, get_redis_client

logger = structlog.get_logger(__name__)

router = APIRouter()


class MemorySearchResult(BaseModel):
    embedding_id: str
    run_id: str
    content: str
    similarity: float
    model: str
    created_at: str


class MemorySearchResponse(BaseModel):
    query: str
    results: list[MemorySearchResult]
    from_cache: bool
    duration_ms: int


class EmbeddingEntry(BaseModel):
    embedding_id: str
    run_id: str
    content: str
    model: str
    created_at: str


@router.get(
    "/search",
    response_model=MemorySearchResponse,
)
async def search_memory(
    x_user_id: str = Header(...),
    q: str = Query(..., min_length=1, max_length=500),
    limit: int = Query(default=10, ge=1, le=50),
    similarity_threshold: float = Query(default=0.35, ge=0.0, le=1.0),
) -> MemorySearchResponse:
    """
    Semantic memory search.
    """

    user_id = x_user_id

    try:
        db_pool = get_db_pool()
        redis_client = get_redis_client()

        if db_pool is None:
            raise RuntimeError("Database pool not initialized")

        if redis_client is None:
            raise RuntimeError("Redis client not initialized")

        agent = MemoryAgent(
            db_pool=db_pool,
            redis_client=redis_client,
        )

        result = await agent.search(
            user_id=user_id,
            query_text=q,
            limit=limit,
            similarity_threshold=similarity_threshold,
        )

        output: dict[str, Any] = result.to_dict()

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

        return MemorySearchResponse(
            query=q,
            results=results,
            from_cache=from_cache,
            duration_ms=duration_ms,
        )

    except Exception as exc:
        logger.error(
            "memory.search.failed",
            user_id=user_id,
            error=str(exc),
        )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        )


@router.get(
    "",
    response_model=list[EmbeddingEntry],
)
async def list_memory(
    x_user_id: str = Header(...),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> list[EmbeddingEntry]:
    """
    List recent memory embeddings.
    """

    user_id = x_user_id

    try:
        db_engine = get_db_engine()

        if db_engine is None:
            raise RuntimeError("Database engine not initialized")

        query = text(
            '''
            SELECT
                em.id::text         AS embedding_id,
                em.run_id::text     AS run_id,
                em.content,
                em.model,
                em.created_at::text AS created_at
            FROM embeddings_metadata em
            JOIN runs r ON r.id = em.run_id
            WHERE r.user_id = :user_id
            ORDER BY em.created_at DESC
            LIMIT :limit OFFSET :offset
            '''
        )

        async with db_engine.begin() as conn:
            result = await conn.execute(
                query,
                {
                    "user_id": user_id,
                    "limit": limit,
                    "offset": offset,
                },
            )

            rows = result.fetchall()

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

    except Exception as exc:
        logger.error(
            "memory.list.failed",
            user_id=user_id,
            error=str(exc),
        )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        )