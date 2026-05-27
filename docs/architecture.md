# NEXUS Architecture

## Overview

NEXUS is a distributed AI agent orchestration platform. A user submits a natural-language query via the Next.js frontend. The API Gateway authenticates the request, creates a run record in PostgreSQL, and dispatches it asynchronously to the Orchestrator. The Orchestrator uses LangGraph to decompose the query into a structured task plan, then executes each task by calling internal agent modules. As the run progresses, events are published to Redis pub/sub and streamed to the browser via Server-Sent Events.

## Services

### API Gateway (`services/gateway/` — port 8000)

Single ingress point for all frontend traffic. Responsibilities:
- JWT authentication via `middleware/auth.py` (Bearer token validated against Redis session store)
- Redis-backed fixed-window rate limiting via `middleware/rate_limit.py`
- Run lifecycle endpoints (`routers/runs.py`): POST to create, GET to list/fetch
- SSE proxy (`routers/sse.py`): proxies the Orchestrator's per-run event stream to the browser
- Memory endpoints (`routers/memory.py`): proxies to Orchestrator memory router
- Metrics endpoints (`routers/metrics.py`): per-user aggregated statistics from PostgreSQL

### Orchestrator (`services/orchestrator/` — port 8001)

The brain of NEXUS. Receives a `POST /orchestrate` call from the Gateway and runs the LangGraph state machine asynchronously. Contains all four agent implementations as internal Python modules under `agents/`:

- **Search Agent** (`agents/search_agent/`): 3-step LLM pipeline — query formulation → web search (Tavily or mock) → re-rank and summarize
- **Code Agent** (`agents/code_agent/`): iterative generate-execute-debug loop using `asyncio` subprocess sandbox
- **Memory Agent** (`agents/memory_agent/`): SentenceTransformer embeddings → pgvector cosine similarity search
- **Tool Agent** (`agents/tool_agent/`): LLM function-calling dispatch to calculator, weather (open-meteo), and Wikipedia

The Orchestrator also exposes:
- `GET /runs/{run_id}/stream`: SSE endpoint that streams Redis pub/sub events to the Gateway
- `GET /memory/search` and `GET /memory`: memory read endpoints called by the Gateway memory router

### LangGraph State Machine (`graph.py`)

Eight nodes wired into a directed graph with conditional edges: