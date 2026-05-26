"""
Shared app.state accessors for orchestrator nodes and internal agents.

The orchestrator's lifespan stores db_engine, db_pool, and redis_client
on app.state. Internal agent modules can't access request.app.state directly,
so this module holds module-level references set during lifespan startup.
"""

from __future__ import annotations

import asyncpg
import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncEngine

_db_engine: AsyncEngine | None = None
_db_pool: asyncpg.Pool | None = None
_redis_client: aioredis.Redis | None = None


def set_db_engine(engine: AsyncEngine) -> None:
    global _db_engine
    _db_engine = engine


def get_db_engine() -> AsyncEngine | None:
    return _db_engine


def set_db_pool(pool: asyncpg.Pool) -> None:
    global _db_pool
    _db_pool = pool


def get_db_pool() -> asyncpg.Pool | None:
    return _db_pool


def set_redis_client(client: aioredis.Redis) -> None:
    global _redis_client
    _redis_client = client


def get_redis_client() -> aioredis.Redis | None:
    return _redis_client