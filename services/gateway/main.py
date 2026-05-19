"""
API Gateway FastAPI application factory.

This module is the entry point for the gateway service. It creates the FastAPI app,
registers all routers, attaches middleware, and manages the lifespan of shared
resources (asyncpg pool, Redis client).

All inbound NEXUS traffic from the frontend passes through this service.
"""

from contextlib import asynccontextmanager
from typing import AsyncIterator

import redis.asyncio as aioredis
import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import create_async_engine, AsyncEngine
from prometheus_fastapi_instrumentator import Instrumentator

from config import settings
from middleware.auth import AuthMiddleware
from middleware.rate_limit import RateLimitMiddleware
from routers import auth, runs

from shared.logging import configure_logging
from shared.telemetry import configure_telemetry
from shared.metrics import configure_metrics

logger = structlog.get_logger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """
    Manage startup and shutdown of shared gateway resources.

    Initialises asyncpg connection pool and Redis client on startup.
    Closes both on shutdown to prevent connection leaks.
    """

    configure_logging(level=settings.log_level)
    configure_telemetry(service_name=settings.service_name, environment=settings.environment)

    # Async SQLAlchemy engine (wraps asyncpg pool)
    engine: AsyncEngine = create_async_engine(
        settings.database_url,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_pool_max_overflow,
        pool_pre_ping=True,
        echo=settings.environment == "development",
    )
    app.state.db_engine = engine

    # Redis async client
    redis_client = aioredis.from_url(
        settings.redis_url,
        encoding="utf-8",
        decode_responses=True,
    )
    app.state.redis = redis_client

    logger.info("gateway.resources_ready")
    yield

    # Shutdown
    logger.info("gateway.shutdown")
    await redis_client.aclose()
    await engine.dispose()

def create_app() -> FastAPI:
    """
    Construct and configure the gateway FastAPI application.

    Returns:
        Fully configured FastAPI instance with all routers and middleware attached.
    """

    app = FastAPI(
        title="NEXUS API Gateway",
        description="Single ingress point for all NEXUS frontend requests.",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if settings.environment == "development" else None,
        redoc_url=None,
    )

    # CORS - allow Next.js dev server and production Vercel origin
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # JWT auth middleware - runs on every request except /api/v1/auth/* and /healthz
    # Starlette executes middleware in reverse registration order.
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(AuthMiddleware)

    # Prometheus metric auto-instrumentation
    Instrumentator().instrument(app).expose(app, endpoint="/metrics")

    # Routers
    app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
    app.include_router(runs.router, prefix="/api/v1/runs", tags=["runs"])

    @app.get("/healthz", tags=["health"])
    async def health_check() -> dict[str, str]:
        """Liveness probe endpoint used by Docker Compose and Railway."""
        return {"status": "ok"}
    
    return app

app = create_app()