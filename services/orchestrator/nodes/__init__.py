"""
Orchestrator node package.

Provides shared Redis client and DB state access for orchestrator nodes
and internal agent modules.
"""

from __future__ import annotations

import redis.asyncio as aioredis
from nodes.app_state import set_redis_client, get_redis_client

__all__ = ["set_redis_client", "get_redis_client"]