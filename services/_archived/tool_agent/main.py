"""
Tool Agent FastAPI application factory.

Exposes:
  POST /run     — LLM tool dispatch pipeline, called by orchestrator dispatch_next_task
  GET  /tools   — Return all tool definitions in LLM tool-use schema format
  GET  /healthz — Liveness probe
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import structlog
from agent import ToolAgent
from config import settings
from fastapi import FastAPI
from llm_provider import get_tool_definitions
from prometheus_fastapi_instrumentator import Instrumentator
from pydantic import BaseModel
from shared.kafka_client import KafkaProducerFactory
from shared.logging import configure_logging
from shared.metrics import configure_metrics
from shared.telemetry import configure_telemetry
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Initialise DB engine and Kafka producer at startup; close on shutdown."""
    configure_logging(level=settings.log_level)
    configure_telemetry(
        service_name=settings.service_name,
        environment=settings.environment,
        app=app,
    )
    configure_metrics()

    engine: AsyncEngine = create_async_engine(
        settings.database_url,
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,
    )
    app.state.db_engine = engine

    try:
        await KafkaProducerFactory.get_producer(bootstrap_servers=settings.kafka_bootstrap_servers)
        logger.info("tool_agent.kafka_producer_ready")
    except Exception as exc:
        logger.warning("tool_agent.kafka_unavailable", error=str(exc))

    logger.info("tool_agent.resources_ready")
    yield

    logger.info("tool_agent.shutdown")
    await KafkaProducerFactory.close()
    await engine.dispose()


class RunRequest(BaseModel):
    """Payload for POST /run — matches dispatch_next_task HTTP contract."""

    run_id: str
    task_id: str
    user_id: str
    task_type: str = "tool"
    input: dict[str, Any]
    attempt: int = 1


class RunResponse(BaseModel):
    """Response from POST /run — matches await_task_result expected shape."""

    output: dict[str, Any] | None = None
    error: str | None = None


def create_app() -> FastAPI:
    """Construct and configure the Tool Agent FastAPI application."""
    app = FastAPI(
        title="NEXUS Tool Agent",
        description="LLM function-calling dispatch: calculator, weather, Wikipedia.",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if settings.environment == "development" else None,
        redoc_url=None,
    )

    Instrumentator().instrument(app).expose(app, endpoint="/metrics")

    @app.get("/healthz", tags=["health"])
    async def health_check() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/tools", tags=["tools"])
    async def list_tools() -> list[dict[str, Any]]:
        """Return all 3 tool definitions in LLM tool-use schema format."""
        return get_tool_definitions()

    @app.post("/run", response_model=RunResponse, tags=["tool"])
    async def run_tool(body: RunRequest) -> RunResponse:
        """
        Execute the tool dispatch pipeline for a dispatched task.

        Args:
            body: RunRequest with run_id, task_id, user_id, input.instruction.

        Returns:
            RunResponse with output dict or error string.
        """
        instruction: str = body.input.get("instruction", "")
        if not instruction:
            return RunResponse(output=None, error="input.instruction is required")

        logger.info(
            "tool_agent.run_request",
            run_id=body.run_id,
            task_id=body.task_id,
            instruction=instruction[:100],
        )

        # Access db_engine from app.state via the app instance
        agent = ToolAgent(db_engine=app.state.db_engine)

        try:
            result = await agent.run(
                task_id=body.task_id,
                run_id=body.run_id,
                user_id=body.user_id,
                instruction=instruction,
            )
            return RunResponse(output=result.to_dict(), error=result.error)
        except Exception as exc:
            logger.error(
                "tool_agent.run_failed",
                run_id=body.run_id,
                task_id=body.task_id,
                error=str(exc),
            )
            return RunResponse(output=None, error=str(exc))

    return app


app = create_app()
