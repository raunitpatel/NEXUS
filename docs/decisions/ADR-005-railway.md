# ADR-005: Railway Deployment and Microservices → Hybrid Architecture Migration

**Status:** Accepted  
**Date:** 2025-05
**Deciders:** NEXUS engineering

---

## Context

### Deployment platform choice

NEXUS requires deployment of: a Next.js frontend, two or more Python backend services, PostgreSQL, and Redis. Three platforms were evaluated: Fly.io, Render, and Railway.

### Architectural migration

The original NEXUS design comprised six independent services, each with its own Dockerfile and FastAPI application:

| Service | Port | Responsibility |
|---|---|---|
| `gateway` | 8000 | Auth, routing, SSE proxy |
| `orchestrator` | 8001 | LangGraph state machine |
| `search_agent` | 8002 | Web search pipeline |
| `code_agent` | 8003 | Code generate-execute-debug |
| `memory_agent` | 8004 | pgvector embed + search |
| `tool_agent` | 8005 | Calculator, weather, Wikipedia |

**Railway free tier limits each project to two active services.** Deploying all six services requires a paid plan ($5+/month per service). For a portfolio project, this is not acceptable.

## Decision

### Deployment: Railway

Use Railway for backend deployment with two services: `gateway` and `orchestrator`.

### Architecture: Hybrid Monolith

Merge all four agent services into the `orchestrator` as internal Python modules under `services/orchestrator/agents/`. The Orchestrator calls agents as direct Python function calls — no HTTP, no Kafka for task dispatch.

Before (microservices):

- orchestrator ──HTTP──► search_agent:8002
- orchestrator ──HTTP──► code_agent:8003
- orchestrator ──HTTP──► memory_agent:8004
- orchestrator ──HTTP──► tool_agent:8005

After (hybrid):

- orchestrator ──Python import──► agents/search_agent/
- orchestrator ──Python import──► agents/code_agent/
- orchestrator ──Python import──► agents/memory_agent/
- orchestrator ──Python import──► agents/tool_agent/

Agent implementations are preserved in full — only the transport layer changes. The `dispatch_next_task.py` node calls agent Python classes directly instead of making `httpx.AsyncClient` HTTP calls.

## Alternatives Considered

### Fly.io

Fly.io's free tier allows 3 shared-CPU VMs. However:
- PostgreSQL add-on is not included free
- Fly.io's Docker deployment model requires `fly.toml` per service — more configuration than Railway
- Railway's GitHub integration is simpler: push to `main` → auto-deploy

### Render

Render's free tier spins down services after 15 minutes of inactivity (cold start on next request). Unacceptable for a demo-able portfolio project.

### Keep all 6 services on Railway paid tier

Estimated cost: ~$30–50/month for 6 services + databases. Not justified for a portfolio project.

### Keep microservices, reduce to 2 Railway services via NGINX multiplexing

Routing all 4 agent services through NGINX on a single Railway service would save slots but create a complex routing layer and make local development harder to mirror production.

## Consequences

**Positive:**
- Fits within Railway free tier (2 services: `gateway` + `orchestrator`)
- Eliminates inter-service HTTP latency for agent calls (function calls are ~0ms vs ~5–50ms HTTP round-trips)
- Eliminates per-agent Kafka dispatch (`nexus.tasks`, `nexus.results` topics are now unused)
- Single Dockerfile for the orchestrator (`services/orchestrator/Dockerfile`) bundles all dependencies including `sentence-transformers`
- Agent code is preserved exactly — only `dispatch_next_task.py` changed from HTTP to Python calls

**Negative:**
- Lost horizontal scalability: agents can no longer scale independently
- The `orchestrator` Docker image is large (~2GB) due to `sentence-transformers` and its torch dependency
- Services in `services/_archived/` (the original standalone agent FastAPI apps) are kept for reference but are not deployed
- `nexus.tasks` and `nexus.results` Kafka topics are provisioned but unused

## Migration Details

### `services/orchestrator/nodes/dispatch_next_task.py`

The node was rewritten to call internal agent Python classes:

```python
# Before — HTTP dispatch
async with httpx.AsyncClient(...) as client:
    response = await client.post(f"{agent_url}/run", json=payload)

# After — direct Python call
from agents.search_agent import SearchAgent
agent = SearchAgent(redis_client=redis_client)
result = await agent.run(task_id=..., run_id=..., query=...)
```

### `services/orchestrator/agents/`

Agent implementations copied from the original microservice directories and refactored to be importable Python classes:

- `agents/search_agent/agent.py` — `SearchAgent` class
- `agents/code_agent/agent.py` — `CodeAgent` class  
- `agents/memory_agent/agent.py` — `MemoryAgent` class
- `agents/tool_agent/agent.py` — `ToolAgent` class

### `services/orchestrator/nodes/app_state.py`

Module-level references to shared resources (db engine, db pool, Redis client) set during FastAPI lifespan, accessible by all agent modules without passing through the LangGraph state.

### Archived services

Original standalone FastAPI services preserved at `services/_archived/` for reference.

## Implementation

- `services/orchestrator/agents/` — all four agent implementations
- `services/orchestrator/nodes/dispatch_next_task.py` — direct Python dispatch
- `services/orchestrator/nodes/app_state.py` — shared state accessors
- `services/orchestrator/Dockerfile` — merged requirements including sentence-transformers
- `railway.toml` — two-service Railway deployment config
- `services/_archived/` — preserved original microservice implementations