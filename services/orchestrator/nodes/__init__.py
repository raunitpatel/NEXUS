"""
Orchestrator node package.

Provides set_redis_client() for wiring the shared async Redis client
into all node functions at startup. Uses the same module-level reference
pattern as set_db_engine() in record_result.py and finalize_run.py.
"""

from __future__ import annotations

import redis.asyncio as aioredis

# Module-level reference — set once by main.py lifespan
_redis_client: aioredis.Redis | None = None


def set_redis_client(client: aioredis.Redis) -> None:
    """
    Store the async Redis client for use by all orchestrator nodes.

    Called once from main.py lifespan after Redis connection is established.

    Args:
        client: Async Redis client from aioredis.from_url().
    """
    global _redis_client
    _redis_client = client