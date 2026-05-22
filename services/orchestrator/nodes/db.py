"""
Shared DB engine accessor for orchestrator nodes.

Provide a single `set_db_engine()` and `get_db_engine()` so all nodes
share the same engine instance and avoid duplicate-module singleton bugs.
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncEngine

_db_engine: AsyncEngine | None = None


def set_db_engine(engine: AsyncEngine) -> None:
    global _db_engine
    _db_engine = engine


def get_db_engine() -> AsyncEngine | None:
    return _db_engine
