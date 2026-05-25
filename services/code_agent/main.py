"""
Code Agent FastAPI application factory.

Exposes:
  POST /run     — execute generate-debug loop, called by orchestrator dispatch_next_task
  GET  /healthz — liveness probe

Redis and Kafka producer are initialised at startup. CodeAgent is stateless and
instantiated per-request.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import structlog
from agent import CodeAgent
from config import settings
from fastapi import FastAPI
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
    Initialise Kafka producer at startup; close on shutdown.
    """
    configure_logging(level=settings.log_level)
    configure_telemetry(
        service_name=settings.service_name,
        environment=settings.environment,
        app=app,
    )
    configure_metrics()

    try:
        await KafkaProducerFactory.get_producer(bootstrap_servers=settings.kafka_bootstrap_servers)
        logger.info("code_agent.kafka_producer_ready")
    except Exception as exc:
        logger.warning("code_agent.kafka_unavailable", error=str(exc))

    logger.info("code_agent.resources_ready")
    yield

    logger.info("code_agent.shutdown")
    await KafkaProducerFactory.close()


# ── Request / response models ─────────────────────────────────────────────────


class RunRequest(BaseModel):
    """
    Payload for POST /run — matches dispatch_next_task HTTP contract.

    Attributes:
        run_id: Parent orchestration run UUID.
        task_id: Task UUID from the tasks table.
        user_id: Authenticated user UUID.
        task_type: Always 'code' for this service.
        input: Dict with at minimum an 'instruction' key.
        attempt: Retry attempt number (1-indexed).
    """

    run_id: str
    task_id: str
    user_id: str
    task_type: str = "code"
    input: dict[str, Any]
    attempt: int = 1


class RunResponse(BaseModel):
    """
    Response from POST /run — matches await_task_result expected shape.

    Attributes:
        output: CodeAgentResult serialised as dict.
        error: Non-null error string on failure.
    """

    output: dict[str, Any] | None = None
    error: str | None = None


# ── App factory ───────────────────────────────────────────────────────────────


def create_app() -> FastAPI:
    """
    Construct and configure the Code Agent FastAPI application.

    Returns:
        Fully configured FastAPI instance.
    """
    app = FastAPI(
        title="NEXUS Code Agent",
        description="Iterative code generation, execution, and debugging.",
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

    @app.post("/run", response_model=RunResponse, tags=["code"])
    async def run_code(body: RunRequest) -> RunResponse:
        """
        Execute the generate-execute-debug loop for a coding instruction.

        Instantiates CodeAgent, runs the loop, and returns structured output.

        Args:
            body: RunRequest with run_id, task_id, user_id, input.instruction.

        Returns:
            RunResponse with output dict or error string.
        """
        instruction: str = body.input.get("instruction", "")
        language: str = body.input.get("language", "python")

        if not instruction:
            return RunResponse(output=None, error="input.instruction is required")

        logger.info(
            "code_agent.run_request",
            run_id=body.run_id,
            task_id=body.task_id,
            instruction=instruction[:100],
        )

        agent = CodeAgent()

        try:
            result = await agent.run(
                task_id=body.task_id,
                run_id=body.run_id,
                user_id=body.user_id,
                instruction=instruction,
                language=language,
            )
            error = None if result.success else "Code execution failed after max iterations"
            return RunResponse(output=result.to_dict(), error=error)
        except Exception as exc:
            logger.error(
                "code_agent.run_failed",
                run_id=body.run_id,
                task_id=body.task_id,
                error=str(exc),
            )
            return RunResponse(output=None, error=str(exc))

    return app


app = create_app()
