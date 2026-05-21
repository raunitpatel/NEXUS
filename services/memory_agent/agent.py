# services/memory_agent/agent.py
"""
Memory Agent core — embed and semantic search over run history.

Two primary operations:
    embed()  — encode text → 384-dim vector → INSERT embeddings_metadata
    search() — encode query → cosine ANN search → cached in Redis

The agent also exposes a Kafka consumer loop (run_kafka_consumer) that
subscribes to nexus.tasks and auto-embeds memory_write task outputs so
other agents' knowledge is stored without explicit orchestrator calls.

Usage (from main.py):
    agent = MemoryAgent(db_pool=pool, redis_client=redis)
    result = await agent.embed(run_id=..., content="text", content_type="task_output")
    results = await agent.search(user_id=..., query_text="semantic query")
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

from config import settings
from embeddings import EmbeddingModel
from pgvector_store import cosine_search, insert_embedding

logger = structlog.get_logger(__name__)

_CACHE_KEY_PREFIX = "vsearch:"


@dataclass
class EmbedResult:
    """
    Return value from MemoryAgent.embed().

    Attributes:
        embedding_id: UUID of the inserted embeddings_metadata row.
        dimensions: Number of dimensions in the stored vector (always 384).
        duration_ms: Wall-clock time for encode + INSERT in milliseconds.
    """

    embedding_id: str
    dimensions: int
    duration_ms: int

    def to_dict(self) -> dict[str, Any]:
        """Serialize for JSON response."""
        return {
            "embedding_id": self.embedding_id,
            "dimensions": self.dimensions,
            "duration_ms": self.duration_ms,
        }


@dataclass
class SearchResult:
    """
    Return value from MemoryAgent.search().

    Attributes:
        results: List of matching content dicts with similarity scores.
        from_cache: True if this response was served from Redis.
        duration_ms: Wall-clock time for the full search operation.
    """

    results: list[dict[str, Any]]
    from_cache: bool
    duration_ms: int

    def to_dict(self) -> dict[str, Any]:
        """Serialize for JSON response."""
        return {
            "results": self.results,
            "from_cache": self.from_cache,
            "duration_ms": self.duration_ms,
        }


class MemoryAgent:
    """
    NEXUS Memory Agent — semantic embedding storage and retrieval.

    Wraps EmbeddingModel (sentence-transformers) + pgvector_store (asyncpg)
    with a Redis cache layer for search results. All LLM calls are absent —
    this service uses only local neural embeddings.

    Attributes:
        _db_pool: asyncpg connection pool to nexus_db.
        _redis: Async Redis client for search result caching.
        _model: Singleton EmbeddingModel instance.
    """

    def __init__(
        self,
        db_pool: asyncpg.Pool,
        redis_client: aioredis.Redis,
    ) -> None:
        """
        Initialize the Memory Agent.

        Args:
            db_pool: asyncpg pool from app.state.db_pool.
            redis_client: Async Redis client from app.state.redis.
        """
        self._db_pool = db_pool
        self._redis = redis_client
        self._model = EmbeddingModel()

    def _make_cache_key(self, user_id: str, query_text: str) -> str:
        """
        Build a deterministic Redis cache key for a user + query pair.

        Format: vsearch:{user_id}:{sha256(query_text)}

        Args:
            user_id: The authenticated user's UUID.
            query_text: The raw query string.

        Returns:
            Redis key string.
        """
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
        """
        Encode text into a 384-dim vector and persist to embeddings_metadata.

        Runs SentenceTransformer.encode() in a ThreadPoolExecutor to avoid
        blocking the asyncio event loop during CPU-bound inference.

        Args:
            run_id: UUID of the parent orchestration run.
            content: The text to embed and store.
            content_type: Semantic label for the content (e.g. "task_output", "user_query").
            task_id: Optional UUID of the originating task.
            user_id: Optional user UUID stored in metadata for filtering.

        Returns:
            EmbedResult with embedding_id, dimensions, and duration_ms.

        Raises:
            asyncpg.PostgresError: If the INSERT fails (e.g. FK violation on run_id).
        """
        start_ms = time.monotonic()

        loop = asyncio.get_event_loop()
        embedding: list[float] = await loop.run_in_executor(
            None, self._model.encode, content
        )

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

        logger.info(
            "memory_agent.embed_complete",
            embedding_id=embedding_id,
            run_id=run_id,
            content_type=content_type,
            duration_ms=duration_ms,
        )

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
        """
        Semantic similarity search over stored embeddings.

        Checks Redis cache first. On miss: encodes query in ThreadPoolExecutor,
        runs pgvector cosine ANN, writes results to Redis with 5-minute TTL.

        Args:
            user_id: The authenticated user's UUID (used in cache key).
            query_text: Natural language query to embed and search.
            limit: Max results to return (defaults to settings.vector_top_k).
            similarity_threshold: Min similarity score (defaults to settings.vector_similarity_threshold).

        Returns:
            SearchResult with results list, from_cache flag, and duration_ms.
        """
        start_ms = time.monotonic()
        effective_limit = limit or settings.vector_top_k
        effective_threshold = similarity_threshold or settings.vector_similarity_threshold
        cache_key = self._make_cache_key(user_id, query_text)

        # Cache read
        try:
            cached_raw = await self._redis.get(cache_key)
            if cached_raw:
                results = json.loads(cached_raw)
                duration_ms = int((time.monotonic() - start_ms) * 1000)
                logger.info(
                    "memory_agent.search_cache_hit",
                    user_id=user_id,
                    cache_key=cache_key,
                    result_count=len(results),
                )
                return SearchResult(results=results, from_cache=True, duration_ms=duration_ms)
        except Exception as exc:
            logger.warning("memory_agent.cache_read_failed", error=str(exc))

        # Cache miss — encode + search
        loop = asyncio.get_event_loop()
        query_embedding: list[float] = await loop.run_in_executor(
            None, self._model.encode, query_text
        )

        results = await cosine_search(
            pool=self._db_pool,
            query_embedding=query_embedding,
            limit=effective_limit,
            similarity_threshold=effective_threshold,
        )

        results.sort(key=lambda r: r["similarity"], reverse=True)

        # Cache write
        try:
            await self._redis.set(
                cache_key,
                json.dumps(results),
                ex=settings.vector_cache_ttl_seconds,
            )
            logger.debug("memory_agent.search_cached", cache_key=cache_key)
        except Exception as exc:
            logger.warning("memory_agent.cache_write_failed", error=str(exc))

        duration_ms = int((time.monotonic() - start_ms) * 1000)

        logger.info(
            "memory_agent.search_complete",
            user_id=user_id,
            result_count=len(results),
            from_cache=False,
            duration_ms=duration_ms,
        )

        return SearchResult(results=results, from_cache=False, duration_ms=duration_ms)


async def run_kafka_consumer(db_pool: asyncpg.Pool, redis_client: aioredis.Redis) -> None:
    """
    Background Kafka consumer that auto-embeds memory_write task outputs.

    Subscribes to nexus.tasks, filters for task_type == 'memory_write',
    extracts the task output content, and calls MemoryAgent.embed().
    Runs as an asyncio background task launched from main.py lifespan.

    Failures on individual messages are logged and swallowed — the consumer
    loop never crashes on bad messages.

    Args:
        db_pool: asyncpg pool for pgvector inserts.
        redis_client: Redis client for search cache invalidation on new embeds.
    """
    from shared.kafka_client import KafkaConsumerFactory
    from shared.kafka_schemas import TaskDispatchedMessage

    agent = MemoryAgent(db_pool=db_pool, redis_client=redis_client)

    logger.info("memory_agent.kafka_consumer.starting")

    try:
        async with KafkaConsumerFactory.create_consumer(
            topic=settings.kafka_topic_tasks,
            bootstrap_servers=settings.kafka_bootstrap_servers,
            group_id=settings.kafka_consumer_group_memory,
            auto_offset_reset="earliest",
        ) as consumer:
            logger.info("memory_agent.kafka_consumer.ready")
            async for msg in consumer:
                try:
                    task = TaskDispatchedMessage.model_validate_json(msg.value)

                    if task.task_type not in ("memory_read", "memory_write"):
                        continue

                    content = task.input.get("content") or task.input.get("query", "")
                    if not content:
                        logger.warning(
                            "memory_agent.kafka_consumer.empty_content",
                            task_id=task.task_id,
                        )
                        continue

                    await agent.embed(
                        run_id=task.run_id,
                        content=content,
                        content_type="kafka_task_input",
                        task_id=task.task_id,
                        user_id=task.user_id,
                    )

                    logger.info(
                        "memory_agent.kafka_consumer.embedded",
                        task_id=task.task_id,
                        run_id=task.run_id,
                    )

                except Exception as exc:
                    logger.error(
                        "memory_agent.kafka_consumer.message_error",
                        error=str(exc),
                    )
    except Exception as exc:
        logger.error("memory_agent.kafka_consumer.fatal", error=str(exc))