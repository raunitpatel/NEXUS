"""
Memory Agent — internal module for the NEXUS Orchestrator.

Previously a standalone FastAPI service (services/memory_agent/).
Now a direct Python import used by nodes/dispatch_next_task.py.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from dataclasses import dataclass
from typing import Any

import asyncpg
import redis.asyncio as aioredis
import structlog
from shared.metrics import agent_task_duration_seconds, agent_tasks_total

logger = structlog.get_logger(__name__)

_CACHE_KEY_PREFIX = "vsearch:"


@dataclass
class EmbedResult:
    embedding_id: str
    dimensions: int
    duration_ms: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "embedding_id": self.embedding_id,
            "dimensions": self.dimensions,
            "duration_ms": self.duration_ms,
        }


@dataclass
class SearchResult:
    results: list[dict[str, Any]]
    from_cache: bool
    duration_ms: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "results": self.results,
            "from_cache": self.from_cache,
            "duration_ms": self.duration_ms,
        }


class MemoryAgent:
    """
    NEXUS Memory Agent — internal Python class, not a FastAPI service.

    Called directly from nodes/dispatch_next_task.py.
    Requires db_pool and redis_client injected from orchestrator app.state.
    """

    def __init__(
        self,
        db_pool: asyncpg.Pool,
        redis_client: aioredis.Redis,
    ) -> None:
        from .embeddings import EmbeddingModel

        self._db_pool = db_pool
        self._redis = redis_client
        self._model = EmbeddingModel()

    def _make_cache_key(self, user_id: str, query_text: str) -> str:
        digest = hashlib.sha256(query_text.encode("utf-8")).hexdigest()
        return f"{_CACHE_KEY_PREFIX}{user_id}:{digest}"

    async def embed(
        self,
        run_id: str,
        content: str,
        content_type: str = "text",
        task_id: str | None = None,
        user_id: str | None = None,
    ) -> EmbedResult:
        from .pgvector_store import insert_embedding

        start_ms = time.monotonic()
        loop = asyncio.get_event_loop()
        embedding: list[float] = await loop.run_in_executor(None, self._model.encode, content)
        metadata: dict[str, Any] = {"content_type": content_type}
        if user_id:
            metadata["user_id"] = user_id

        embedding_id = await insert_embedding(
            pool=self._db_pool,
            run_id=run_id,
            content=content,
            embedding=embedding,
            task_id=task_id,
            metadata=metadata,
        )
        duration_ms = int((time.monotonic() - start_ms) * 1000)
        agent_task_duration_seconds.labels(agent="memory-embed", status="success").observe(duration_ms / 1000)
        agent_tasks_total.labels(agent="memory-embed", status="success").inc()
        return EmbedResult(
            embedding_id=embedding_id,
            dimensions=self._model.dimensions,
            duration_ms=duration_ms,
        )

    async def search(
        self,
        user_id: str,
        query_text: str,
        limit: int | None = None,
        similarity_threshold: float | None = None,
    ) -> SearchResult:
        from config import settings
        from .pgvector_store import cosine_search

        start_ms = time.monotonic()
        effective_limit = limit or settings.vector_top_k
        effective_threshold = similarity_threshold or settings.vector_similarity_threshold
        cache_key = self._make_cache_key(user_id, query_text)

        try:
            cached_raw = await self._redis.get(cache_key)
            if cached_raw:
                results = json.loads(cached_raw)
                duration_ms = int((time.monotonic() - start_ms) * 1000)
                return SearchResult(results=results, from_cache=True, duration_ms=duration_ms)
        except Exception as exc:
            logger.warning("memory_agent.cache_read_failed", error=str(exc))

        loop = asyncio.get_event_loop()
        query_embedding: list[float] = await loop.run_in_executor(None, self._model.encode, query_text)
        results = await cosine_search(
            pool=self._db_pool,
            query_embedding=query_embedding,
            limit=effective_limit,
            similarity_threshold=effective_threshold,
        )
        results.sort(key=lambda r: r["similarity"], reverse=True)

        try:
            from config import settings as _s
            await self._redis.set(
                cache_key,
                json.dumps(results),
                ex=_s.vector_cache_ttl_seconds,
            )
        except Exception as exc:
            logger.warning("memory_agent.cache_write_failed", error=str(exc))

        duration_ms = int((time.monotonic() - start_ms) * 1000)
        agent_task_duration_seconds.labels(agent="memory-search", status="success").observe(duration_ms / 1000)
        agent_tasks_total.labels(agent="memory-search", status="success").inc()
        return SearchResult(results=results, from_cache=False, duration_ms=duration_ms)