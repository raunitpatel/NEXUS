"""
Search Agent FastAPI application factory.

Exposes:
  POST /run     — execute search pipeline, called by orchestrator dispatch_next_task
  GET  /healthz — liveness probe

Redis and Kafka producer are initialised at startup and stored on app.state.
SearchAgent is instantiated per-request (stateless, takes redis from app.state).
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import redis.asyncio as aioredis
import structlog
from agent import SearchAgent
from config import settings
from fastapi import FastAPI, Request
from prometheus_fastapi_instrumentator import Instrumentator
from pydantic import BaseModel
from shared.kafka_client import KafkaProducerFactory
from shared.logging import configure_logging
from shared.metrics import configure_metrics
from shared.telemetry import configure_telemetry

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """
    Initialise Redis and Kafka producer at startup; close both on shutdown.
    """
    configure_logging(level=settings.log_level)
    configure_telemetry(
        service_name=settings.service_name,
        environment=settings.environment,
        app=app,
    )
    configure_metrics()

    redis_client = aioredis.from_url(
        settings.redis_url,
        encoding="utf-8",
        decode_responses=True,
    )
    app.state.redis = redis_client

    # Warm up Kafka producer connection at startup
    try:
        await KafkaProducerFactory.get_producer(bootstrap_servers=settings.kafka_bootstrap_servers)
        logger.info("search_agent.kafka_producer_ready")
    except Exception as exc:
        logger.warning("search_agent.kafka_unavailable", error=str(exc))

    logger.info("search_agent.resources_ready")
    yield

    logger.info("search_agent.shutdown")
    await redis_client.aclose()
    await KafkaProducerFactory.close()


# ── Request / response models ─────────────────────────────────────────────────


class RunRequest(BaseModel):
    """
    Payload for POST /run — matches dispatch_next_task HTTP contract.

    Attributes:
        run_id: Parent orchestration run UUID.
        task_id: Task UUID from the tasks table.
        user_id: Authenticated user UUID.
        task_type: Always 'search' for this service.
        input: Dict with at minimum a 'query' key.
        attempt: Retry attempt number (1-indexed).
    """

    run_id: str
    task_id: str
    user_id: str
    task_type: str = "search"
    input: dict[str, Any]
    attempt: int = 1


class RunResponse(BaseModel):
    """
    Response from POST /run — matches await_task_result expected shape.

    Attributes:
        output: SearchAgentResult serialised as dict.
        error: Non-null error string on failure.
    """

    output: dict[str, Any] | None = None
    error: str | None = None


# ── App factory ───────────────────────────────────────────────────────────────


def create_app() -> FastAPI:
    """
    Construct and configure the Search Agent FastAPI application.

    Returns:
        Fully configured FastAPI instance.
    """
    app = FastAPI(
        title="NEXUS Search Agent",
        description="Query formulation, web search, and result summarization.",
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

    @app.post("/run", response_model=RunResponse, tags=["search"])
    async def run_search(body: RunRequest, request: Request) -> RunResponse:
        """
        Execute the search pipeline for a dispatched task.

        Instantiates SearchAgent with the app-level Redis client, runs the
        three-call LLM pipeline, and returns structured output.

        Args:
            body: RunRequest with run_id, task_id, user_id, input.query.
            request: FastAPI Request for accessing app.state.redis.

        Returns:
            RunResponse with output dict or error string.
        """
        query: str = body.input.get("query", "")
        if not query:
            return RunResponse(output=None, error="input.query is required")

        logger.info(
            "search_agent.run_request",
            run_id=body.run_id,
            task_id=body.task_id,
            query=query[:100],
        )

        agent = SearchAgent(redis_client=request.app.state.redis)

        try:
            result = await agent.run(
                task_id=body.task_id,
                run_id=body.run_id,
                user_id=body.user_id,
                query=query,
            )
            return RunResponse(output=result.to_dict(), error=None)
        except Exception as exc:
            logger.error(
                "search_agent.run_failed",
                run_id=body.run_id,
                task_id=body.task_id,
                error=str(exc),
            )
            return RunResponse(output=None, error=str(exc))

    return app


app = create_app()
