"""
Orchestrator FastAPI application factory.

Entry point for the orchestrator service. Compiles the LangGraph graph once
at startup, stores it on app.state, and exposes POST /orchestrate which
dispatches graph execution as a background asyncio task — returning
{run_id, status: "running"} immediately to meet the 100ms latency requirement.
"""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
import structlog
from config import settings
from fastapi import FastAPI
from graph import build_graph
from prometheus_fastapi_instrumentator import Instrumentator
from pydantic import BaseModel
from shared.logging import configure_logging
from shared.metrics import active_runs, configure_metrics, orchestrator_runs_total
from shared.telemetry import configure_telemetry
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from state import OrchestratorState

logger = structlog.get_logger(__name__)

# Lifespan


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """
    Manage startup and shutdown of shared orchestrator resources.

    Compiles the LangGraph graph, initialises the async DB engine, and
    connects to Redis on startup. Disposes all on shutdown.
    """
    configure_logging(level=settings.log_level)
    configure_telemetry(
        service_name=settings.service_name,
        environment=settings.environment,
        app=app,
    )
    configure_metrics()

    # Compile LangGraph graph — done once at startup, never per-request
    app.state.graph = build_graph
    app.state.graph = build_graph()
    logger.info("orchestrator.graph_compiled")

    engine: AsyncEngine = create_async_engine(
        settings.database_url,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_pool_max_overflow,
        pool_pre_ping=True,
    )

    from nodes.db import set_db_engine as set_shared_db_engine

    # Set the single shared DB engine for all orchestrator nodes
    set_shared_db_engine(engine)
    app.state.db_engine = engine

    redis_client = aioredis.from_url(
        settings.redis_url,
        encoding="utf-8",
        decode_responses=False,
    )
    app.state.redis = redis_client

    from nodes import set_redis_client

    set_redis_client(redis_client)
    logger.info("orchestrator.redis_wired_to_nodes")

    logger.info("orchestrator.resources_ready")
    yield

    logger.info("orchestrator.shutdown")
    await redis_client.aclose()
    await engine.dispose()


# Request / response models


class OrchestrateRequest(BaseModel):
    """
    Payload for POST /orchestrate.

    Attributes:
        run_id: UUID of the runs row already written by the Gateway.
        query: Raw user query string.
        user_id: UUID of the authenticated user.
    """

    run_id: str
    query: str
    user_id: str


class OrchestrateResponse(BaseModel):
    """
    Response returned immediately from POST /orchestrate.

    Graph runs asynchronously — response is sent before graph completes.

    Attributes:
        run_id: Echoed from the request.
        status: Always 'running' for a successful dispatch.
    """

    run_id: str
    status: str


def create_app() -> FastAPI:
    """
    Construct and configure the orchestrator FastAPI application.

    Returns:
        Fully configured FastAPI instance.
    """
    app = FastAPI(
        title="NEXUS Orchestrator",
        description="LangGraph-powered multi-agent orchestration service.",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if settings.environment == "development" else None,
        redoc_url=None,
    )

    Instrumentator().instrument(app).expose(app, endpoint="/metrics")

    from routers.sse import router as sse_router

    app.include_router(sse_router, tags=["sse"])

    @app.get("/healthz", tags=["health"])
    async def health_check() -> dict[str, str]:
        """Liveness probe used by Docker Compose and Railway."""
        return {"status": "ok"}

    @app.post(
        "/orchestrate",
        response_model=OrchestrateResponse,
        tags=["orchestrate"],
        summary="Launch an agent orchestration run",
    )
    async def orchestrate(body: OrchestrateRequest) -> OrchestrateResponse:
        """
        Accept a run request and launch the LangGraph graph as a background task.

        Returns {run_id, status: "running"} immediately. The graph executes
        in the background via asyncio.ensure_future and updates the runs row
        in Postgres when complete (implemented in AGNT-010).

        Args:
            body: OrchestrateRequest with run_id, query, user_id.

        Returns:
            OrchestrateResponse confirming the run has been dispatched.
        """
        initial_state: OrchestratorState = {
            "run_id": body.run_id,
            "user_id": body.user_id,
            "query": body.query,
            "task_plan": [],
            "completed_tasks": [],
            "pending_task": None,
            "task_result": None,
            "retry_count": 0,
            "final_output": None,
            "status": "running",
            "error": None,
            "input_tokens": 0,
            "output_tokens": 0,
            "metadata": {},
        }

        asyncio.ensure_future(_run_graph(app.state.graph, initial_state, body.run_id))

        logger.info(
            "orchestrator.run_dispatched",
            run_id=body.run_id,
            user_id=body.user_id,
        )
        return OrchestrateResponse(run_id=body.run_id, status="running")

    return app


async def _run_graph(
    graph: object,
    state: OrchestratorState,
    run_id: str,
) -> None:
    """
    Execute the compiled LangGraph graph for a single run.

    Wraps graph.ainvoke in try/except so background failures are logged
    rather than silently swallowed by the asyncio event loop.

    Args:
        graph: Compiled CompiledStateGraph from build_graph().
        state: Initial OrchestratorState for this run.
        run_id: Run UUID string for structured log correlation.
    """
    active_runs.labels(service="orchestrator").inc()
    try:
        await graph.ainvoke(state)  # type: ignore[attr-defined]
        logger.info("orchestrator.run_complete", run_id=run_id)
        orchestrator_runs_total.labels(status="completed").inc()
    except Exception as exc:
        logger.error(
            "orchestrator.run_failed",
            run_id=run_id,
            error=str(exc),
        )
        orchestrator_runs_total.labels(status="failed").inc()
    finally:
        active_runs.labels(service="orchestrator").dec()


app = create_app()
