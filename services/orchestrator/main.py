"""
Orchestrator FastAPI application factory.

Hybrid Railway architecture: agents are internal Python modules, not
standalone services. The orchestrator is the only internal backend service.
"""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import asyncpg
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


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """
    Manage startup and shutdown of shared orchestrator resources.

    In the hybrid architecture, also initialises:
    - asyncpg pool for the memory agent (pgvector operations)
    - Sets all shared state references used by internal agent modules
    """
    configure_logging(level=settings.log_level)
    configure_telemetry(
        service_name=settings.service_name,
        environment=settings.environment,
        app=app,
    )
    configure_metrics()

    app.state.graph = build_graph()
    logger.info("orchestrator.graph_compiled")

    # SQLAlchemy async engine (used by orchestrator nodes + tool agent)
    engine: AsyncEngine = create_async_engine(
        settings.database_url,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_pool_max_overflow,
        pool_pre_ping=True,
    )

    # asyncpg pool (used by memory agent's pgvector_store)
    asyncpg_dsn = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
    db_pool: asyncpg.Pool = await asyncpg.create_pool(
        asyncpg_dsn,
        min_size=2,
        max_size=10,
        command_timeout=30,
    )

    redis_client = aioredis.from_url(
        settings.redis_url,
        encoding="utf-8",
        decode_responses=False,
    )

    # Wire shared state for nodes and internal agent modules
    from nodes.app_state import set_db_engine, set_db_pool, set_redis_client as set_state_redis
    from nodes.db import set_db_engine as set_node_db_engine
    from nodes import set_redis_client

    set_db_engine(engine)
    set_node_db_engine(engine)
    set_db_pool(db_pool)
    set_state_redis(redis_client)
    set_redis_client(redis_client)

    app.state.db_engine = engine
    app.state.db_pool = db_pool
    app.state.redis = redis_client

    # Pre-load sentence-transformers model so first memory request is fast
    try:
        from agents.memory_agent.embeddings import EmbeddingModel
        EmbeddingModel()
        logger.info("orchestrator.embedding_model_preloaded")
    except Exception as exc:
        logger.warning("orchestrator.embedding_model_preload_failed", error=str(exc))

    logger.info("orchestrator.resources_ready", mode="hybrid_railway")
    yield

    logger.info("orchestrator.shutdown")
    await redis_client.aclose()
    await db_pool.close()
    await engine.dispose()


class OrchestrateRequest(BaseModel):
    run_id: str
    query: str
    user_id: str


class OrchestrateResponse(BaseModel):
    run_id: str
    status: str


def create_app() -> FastAPI:
    app = FastAPI(
        title="NEXUS Orchestrator",
        description="LangGraph multi-agent orchestration — hybrid Railway architecture.",
        version="0.2.0",
        lifespan=lifespan,
        docs_url="/docs" if settings.environment == "development" else None,
        redoc_url=None,
    )

    Instrumentator().instrument(app).expose(app, endpoint="/metrics")

    from routers.sse import router as sse_router
    app.include_router(sse_router, tags=["sse"])
    from routers import memory
    app.include_router( memory.router, prefix="/memory", tags=["memory"])

    @app.get("/healthz", tags=["health"])
    async def health_check() -> dict[str, str]:
        return {"status": "ok"}

    @app.post(
        "/orchestrate",
        response_model=OrchestrateResponse,
        tags=["orchestrate"],
        summary="Launch an agent orchestration run",
    )
    async def orchestrate(body: OrchestrateRequest) -> OrchestrateResponse:
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
        logger.info("orchestrator.run_dispatched", run_id=body.run_id, user_id=body.user_id)
        return OrchestrateResponse(run_id=body.run_id, status="running")

    return app


async def _run_graph(
    graph: object,
    state: OrchestratorState,
    run_id: str,
) -> None:
    active_runs.labels(service="orchestrator").inc()
    try:
        await graph.ainvoke(state)  # type: ignore[attr-defined]
        logger.info("orchestrator.run_complete", run_id=run_id)
        orchestrator_runs_total.labels(status="completed").inc()
    except Exception as exc:
        logger.error("orchestrator.run_failed", run_id=run_id, error=str(exc))
        orchestrator_runs_total.labels(status="failed").inc()
    finally:
        active_runs.labels(service="orchestrator").dec()


app = create_app()