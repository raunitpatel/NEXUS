"""
Memory Agent FastAPI application factory.

Exposes:
  POST /run     — embed or search, dispatched by task_type field
  GET  /healthz — liveness probe

asyncpg pool and Redis client are initialised at startup.
SentenceTransformer model is loaded during lifespan to avoid cold-start on
first request. Kafka consumer is launched as a background asyncio task.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

import asyncpg
import redis.asyncio as aioredis
import structlog
from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator
from pydantic import BaseModel

from agent import MemoryAgent, run_kafka_consumer
from config import settings
from embeddings import EmbeddingModel
from shared.logging import configure_logging
from shared.metrics import configure_metrics
from shared.telemetry import configure_telemetry

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """
    Initialise asyncpg pool, Redis client, embedding model, and Kafka consumer.

    The SentenceTransformer model is loaded here (blocking ~2s CPU) so the
    first /run request is not delayed. Kafka consumer runs as a background task.
    """
    configure_logging(level=settings.log_level)
    configure_telemetry(
        service_name=settings.service_name,
        environment=settings.environment,
    )
    configure_metrics()

    # asyncpg pool — strips SQLAlchemy prefix for direct asyncpg use
    dsn = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
    db_pool: asyncpg.Pool = await asyncpg.create_pool(
        dsn,
        min_size=2,
        max_size=10,
        command_timeout=30,
    )
    app.state.db_pool = db_pool

    redis_client = aioredis.from_url(
        settings.redis_url,
        encoding="utf-8",
        decode_responses=True,
    )
    app.state.redis = redis_client

    # Warm up embedding model — loads from HuggingFace cache into memory
    try:
        EmbeddingModel()
        logger.info("memory_agent.model_ready", model=settings.embedding_model_name)
    except Exception as exc:
        logger.error("memory_agent.model_load_failed", error=str(exc))
        raise

    # Background Kafka consumer
    consumer_task = asyncio.ensure_future(
        run_kafka_consumer(db_pool=db_pool, redis_client=redis_client)
    )
    app.state.consumer_task = consumer_task

    logger.info("memory_agent.resources_ready")
    yield

    logger.info("memory_agent.shutdown")
    consumer_task.cancel()
    await redis_client.aclose()
    await db_pool.close()


# ── Request / response models ─────────────────────────────────────────────────

class RunRequest(BaseModel):
    """
    Payload for POST /run — matches dispatch_next_task HTTP contract.

    task_type determines whether this is an embed (memory_write) or
    search (memory_read) operation.

    Attributes:
        run_id: Parent orchestration run UUID.
        task_id: Task UUID from the tasks table.
        user_id: Authenticated user UUID.
        task_type: 'memory_write' (embed) or 'memory_read' (search).
        input: For memory_write: {content, content_type}. For memory_read: {query}.
        attempt: Retry attempt number (1-indexed).
    """

    run_id: str
    task_id: str
    user_id: str
    task_type: str
    input: dict[str, Any]
    attempt: int = 1


class RunResponse(BaseModel):
    """
    Response from POST /run — matches await_task_result expected shape.

    Attributes:
        output: EmbedResult or SearchResult serialised as dict.
        error: Non-null error string on failure.
    """

    output: dict[str, Any] | None = None
    error: str | None = None


# ── App factory ───────────────────────────────────────────────────────────────

def create_app() -> FastAPI:
    """
    Construct and configure the Memory Agent FastAPI application.

    Returns:
        Fully configured FastAPI instance.
    """
    app = FastAPI(
        title="NEXUS Memory Agent",
        description="Semantic embedding storage and retrieval via pgvector.",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if settings.environment == "development" else None,
        redoc_url=None,
    )

    Instrumentator().instrument(app).expose(app, endpoint="/metrics")

    @app.get("/healthz", tags=["health"])
    async def health_check() -> dict[str, str]:
        """Liveness probe used by Docker Compose and Railway."""
        return {"status": "ok"}

    @app.post("/run", response_model=RunResponse, tags=["memory"])
    async def run_memory(body: RunRequest) -> RunResponse:
        """
        Dispatch a memory_write (embed) or memory_read (search) operation.

        Routes to MemoryAgent.embed() for memory_write and
        MemoryAgent.search() for memory_read based on task_type.

        Args:
            body: RunRequest with run_id, task_id, user_id, task_type, input.

        Returns:
            RunResponse with output dict or error string.
        """
        from fastapi import Request
        agent = MemoryAgent(
            db_pool=app.state.db_pool,
            redis_client=app.state.redis,
        )

        logger.info(
            "memory_agent.run_request",
            run_id=body.run_id,
            task_id=body.task_id,
            task_type=body.task_type,
        )

        try:
            if body.task_type == "memory_write":
                content = body.input.get("content", "")
                if not content:
                    return RunResponse(output=None, error="input.content is required for memory_write")

                result = await agent.embed(
                    run_id=body.run_id,
                    content=content,
                    content_type=body.input.get("content_type", "task_output"),
                    task_id=body.task_id,
                    user_id=body.user_id,
                )
                return RunResponse(output=result.to_dict(), error=None)

            elif body.task_type == "memory_read":
                query = body.input.get("query", "")
                if not query:
                    return RunResponse(output=None, error="input.query is required for memory_read")

                result = await agent.search(
                    user_id=body.user_id,
                    query_text=query,
                    limit=body.input.get("limit"),
                    similarity_threshold=body.input.get("similarity_threshold"),
                )
                return RunResponse(output=result.to_dict(), error=None)

            else:
                return RunResponse(
                    output=None,
                    error=f"Unknown task_type '{body.task_type}'. Expected 'memory_write' or 'memory_read'.",
                )

        except Exception as exc:
            logger.error(
                "memory_agent.run_failed",
                run_id=body.run_id,
                task_id=body.task_id,
                error=str(exc),
            )
            return RunResponse(output=None, error=str(exc))

    return app


app = create_app()