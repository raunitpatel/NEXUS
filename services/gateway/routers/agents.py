"""
Agents router for the API Gateway.

Endpoints:
  GET ""         — list all active agents with health status
  GET "/{agent_id}" — get a single agent by ID

Agent rows are seeded by db/seed.py (AGENT_DEFINITIONS). Health status is
determined by calling GET /healthz on each agent's base_url via httpx.
All endpoints require a valid JWT.
"""

from __future__ import annotations

import asyncio
from typing import Annotated

import httpx
import structlog
from dependencies import get_current_user, get_db_session
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)
router = APIRouter()


# ── Response models ───────────────────────────────────────────────────────────


class AgentResponse(BaseModel):
    """
    Agent representation returned by the API.

    Attributes:
        agent_id: UUID of the agent row.
        name: Display name (e.g. "Search Agent").
        type: Agent type slug (search/code/memory/tool/orchestrator).
        base_url: Internal Docker service URL.
        description: Human-readable description.
        is_active: Whether the agent is enabled in the DB.
        is_healthy: Whether the agent's /healthz returned 200 within 3s.
            None if health check was skipped (agent not active).
    """

    agent_id: str
    name: str
    type: str
    base_url: str
    description: str | None
    is_active: bool
    is_healthy: bool | None = None


# ── Helpers ───────────────────────────────────────────────────────────────────


async def _check_health(base_url: str) -> bool:
    """
    Call GET /healthz on an agent service and return True if it responds 200.

    Uses a short 3-second timeout so the list endpoint stays fast even if
    an agent is down. Never raises — returns False on any error.

    Args:
        base_url: Internal Docker service base URL (e.g. "http://search-agent:8002").

    Returns:
        True if the agent responded with HTTP 200, False otherwise.
    """
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.get(f"{base_url}/healthz")
            return response.status_code == 200
    except Exception:
        return False


async def _check_all_health(agents: list[dict]) -> dict[str, bool]:
    """
    Check health of all active agents concurrently.

    Fires all /healthz calls in parallel with asyncio.gather so the total
    latency is bounded by the slowest single agent (not the sum of all).

    Args:
        agents: List of agent row dicts with 'agent_id' and 'base_url' keys.

    Returns:
        Dict mapping agent_id → is_healthy bool.
    """
    tasks = [_check_health(a["base_url"]) for a in agents]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    return {
        a["agent_id"]: bool(r) if not isinstance(r, Exception) else False
        for a, r in zip(agents, results, strict = False)
    }


# ── GET /api/v1/agents ────────────────────────────────────────────────────────


@router.get(
    "",
    response_model=list[AgentResponse],
    summary="List all agents with live health status",
)
async def list_agents(
    current_user: Annotated[dict[str, str], Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[AgentResponse]:
    """
    Return all agents from the agents table with live /healthz status.

    Health checks are fired concurrently — total latency is ~3s worst case
    (the /healthz timeout) not 3s × number of agents.

    Args:
        current_user: Injected by get_current_user.
        db: Injected async SQLAlchemy session.

    Returns:
        List of AgentResponse objects, active agents first.
    """
    result = await db.execute(
        text(
            """
            SELECT
                id::text     AS agent_id,
                name,
                type,
                base_url,
                description,
                is_active
            FROM agents
            ORDER BY is_active DESC, name ASC
            """
        )
    )
    rows = result.fetchall()

    agents = [
        {
            "agent_id": row.agent_id,
            "name": row.name,
            "type": row.type,
            "base_url": row.base_url,
            "description": row.description,
            "is_active": row.is_active,
        }
        for row in rows
    ]

    # Only health-check active agents
    active_agents = [a for a in agents if a["is_active"]]
    health_map = await _check_all_health(active_agents)

    logger.info("agents.list", count=len(agents), user_id=current_user["user_id"])

    return [
        AgentResponse(
            agent_id=a["agent_id"],
            name=a["name"],
            type=a["type"],
            base_url=a["base_url"],
            description=a["description"],
            is_active=a["is_active"],
            is_healthy=health_map.get(a["agent_id"]) if a["is_active"] else None,
        )
        for a in agents
    ]


# ── GET /api/v1/agents/{agent_id} ─────────────────────────────────────────────


@router.get(
    "/{agent_id}",
    response_model=AgentResponse,
    summary="Get a single agent by ID with health status",
)
async def get_agent(
    agent_id: str,
    current_user: Annotated[dict[str, str], Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> AgentResponse:
    """
    Return a single agent by UUID with live /healthz status.

    Args:
        agent_id: UUID string of the agent to fetch.
        current_user: Injected by get_current_user.
        db: Injected async SQLAlchemy session.

    Returns:
        AgentResponse with current health status.

    Raises:
        HTTPException 404: If agent not found.
    """
    result = await db.execute(
        text(
            """
            SELECT
                id::text     AS agent_id,
                name,
                type,
                base_url,
                description,
                is_active
            FROM agents
            WHERE id = :agent_id
            """
        ),
        {"agent_id": agent_id},
    )
    row = result.fetchone()

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent {agent_id} not found",
        )

    is_healthy = None
    if row.is_active:
        is_healthy = await _check_health(row.base_url)

    logger.info("agents.get", agent_id=agent_id, user_id=current_user["user_id"])

    return AgentResponse(
        agent_id=row.agent_id,
        name=row.name,
        type=row.type,
        base_url=row.base_url,
        description=row.description,
        is_active=row.is_active,
        is_healthy=is_healthy,
    )
