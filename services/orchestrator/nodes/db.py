"""
Shared DB engine accessor — delegates to nodes.app_state for consistency.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncEngine
from nodes.app_state import set_db_engine as _set, get_db_engine as _get


def set_db_engine(engine: AsyncEngine) -> None:
    _set(engine)


def get_db_engine() -> AsyncEngine | None:
    return _get()