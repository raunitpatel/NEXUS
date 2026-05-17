"""
FastAPI dependency injection functions for the gateway service.

All route handlers that need the database or Redis must declare these
as FastAPI Depends() parameters — never access request.app.state directly.
"""

from typing import AsyncIterator
import redis.asyncio as aioredis
import structlog
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

logger = structlog.get_logger(__name__)

async def get_db_session(request: Request) -> AsyncIterator[AsyncSession]:
    """
    Yield an async SQLAlchemy session from the engine stored in app.state.

    The session is automatically closed after the request completes.
    Rolls back on exception to prevent dirty state.
    """

    session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
        bind=request.app.state.db_engine,
        expire_on_commit=False,
        autoflush=False,
    )
    async with session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise

async def get_redis(request: Request) -> aioredis.Redis:
    """
    Return the shared Redis async client from app.state.

    Returns:
        Shared aioredis.Redis instance — do not close it; it is managed by lifespan.
    """
    return request.app.state.redis

async def get_current_user(request: Request) -> dict[str, str]:
    """
    Extract the authenticated user from request.state.

    Set by AuthMiddleware after successful JWT validation.
    Raises 401 if the middleware did not populate current_user
    (which should not happen in practice — the middleware blocks first).

    Returns:
        Dict with keys: user_id (str), jti (str)
    """

    current_user: dict[str, str] | None = getattr(request.state, "current_user", None)
    if current_user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return current_user