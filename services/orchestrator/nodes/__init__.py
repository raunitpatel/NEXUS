"""
Orchestrator node package.

Provides shared Redis client access for orchestrator nodes.
"""

from __future__ import annotations

import redis.asyncio as aioredis

# Shared mutable singleton
_redis_client: aioredis.Redis | None = None


def set_redis_client(client: aioredis.Redis) -> None:
    """
    Store the async Redis client globally.
    """
    global _redis_client
    _redis_client = client


def get_redis_client() -> aioredis.Redis | None:
    """
    Return the currently configured Redis client.
    """
    return _redis_client
