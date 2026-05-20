"""
asyncpg + pgvector store for the NEXUS Memory Agent.

All direct database operations live here. The MemoryAgent class in agent.py
calls these functions — it never touches asyncpg directly.

Two operations are exposed:
    insert_embedding()  — INSERT into embeddings_metadata
    cosine_search()     — SELECT ... ORDER BY embedding <=> $1::vector LIMIT $2

The <=> operator is pgvector's cosine distance (0.0 = identical, 2.0 = opposite).
We convert to similarity as: similarity = 1.0 - (distance / 2.0), which maps
perfectly to the [0.0, 1.0] range since all-MiniLM-L6-v2 uses normalize_embeddings=True.

Usage:
    pool = await asyncpg.create_pool(dsn)
    await insert_embedding(pool, run_id=..., content="text", vector=[...])
    results = await cosine_search(pool, query_vector=[...], limit=5)
"""

from __future__ import annotations

import json
from typing import Any

import asyncpg
import structlog

logger = structlog.get_logger(__name__)


async def insert_embedding(
    pool: asyncpg.Pool,
    run_id: str,
    content: str,
    embedding: list[float],
    task_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    model: str = "all-MiniLM-L6-v2",
) -> str:
    """
    Insert a content embedding row into embeddings_metadata.

    Serializes the embedding vector to pgvector-compatible string format
    '[f1,f2,...,f384]' and casts via ::vector in the SQL query.

    Args:
        pool: asyncpg connection pool from app.state.db_pool.
        run_id: UUID of the parent orchestration run (FK to runs.id).
        content: Raw text that was embedded — stored for retrieval display.
        embedding: 384-element float list from EmbeddingModel.encode().
        task_id: Optional UUID of the related task (FK to tasks.id).
        metadata: Optional JSONB metadata dict (source, content_type, etc.).
        model: Embedding model name — must match embeddings_model_values CHECK.

    Returns:
        UUID string of the newly inserted embeddings_metadata row.

    Raises:
        asyncpg.PostgresError: On constraint violation or connection failure.
    """
    vector_str = "[" + ",".join(str(f) for f in embedding) + "]"
    meta_json = json.dumps(metadata or {})

    row = await pool.fetchrow(
        """
        INSERT INTO embeddings_metadata (run_id, task_id, content, embedding, model, metadata)
        VALUES ($1, $2, $3, $4::vector, $5, $6::jsonb)
        RETURNING id::text
        """,
        run_id,
        task_id,
        content,
        vector_str,
        model,
        meta_json,
    )

    embedding_id: str = row["id"]

    logger.info(
        "pgvector_store.inserted",
        embedding_id=embedding_id,
        run_id=run_id,
        content_length=len(content),
    )

    return embedding_id


async def cosine_search(
    pool: asyncpg.Pool,
    query_embedding: list[float],
    limit: int = 10,
    similarity_threshold: float = 0.75,
) -> list[dict[str, Any]]:
    """
    Perform approximate nearest-neighbour cosine similarity search on embeddings_metadata.

    Uses the pgvector <=> operator (cosine distance) with the IVFFlat index
    defined in db/schema.sql. Converts distance to similarity: 1.0 - (distance / 2.0).
    Filters to results above similarity_threshold before returning.

    Args:
        pool: asyncpg connection pool.
        query_embedding: 384-element float list for the query.
        limit: Maximum number of results to return (default from config.vector_top_k).
        similarity_threshold: Minimum similarity score to include in results.

    Returns:
        List of dicts with keys: id, run_id, task_id, content, similarity,
        model, metadata, created_at. Ordered by similarity descending.

    Raises:
        asyncpg.PostgresError: On query failure.
    """
    vector_str = "[" + ",".join(str(f) for f in query_embedding) + "]"

    rows = await pool.fetch(
        """
        SELECT
            id::text,
            run_id::text,
            task_id::text,
            content,
            model,
            metadata,
            created_at,
            1.0 - (embedding <=> $1::vector) / 2.0 AS similarity
        FROM embeddings_metadata
        WHERE 1.0 - (embedding <=> $1::vector) / 2.0 >= $3
        ORDER BY embedding <=> $1::vector ASC
        LIMIT $2
        """,
        vector_str,
        limit,
        similarity_threshold,
    )

    results = [
        {
            "id": row["id"],
            "run_id": row["run_id"],
            "task_id": row["task_id"],
            "content": row["content"],
            "similarity": float(row["similarity"]),
            "model": row["model"],
            "metadata": row["metadata"] or {},
            "created_at": row["created_at"].isoformat(),
        }
        for row in rows
    ]

    logger.info(
        "pgvector_store.search_complete",
        result_count=len(results),
        limit=limit,
        threshold=similarity_threshold,
    )

    return results