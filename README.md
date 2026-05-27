# NEXUS

**Distributed AI Agent Orchestration Platform**

[![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Next.js](https://img.shields.io/badge/Next.js-14-000000?logo=next.js&logoColor=white)](https://nextjs.org)
[![LangGraph](https://img.shields.io/badge/LangGraph-0.1-FF6B35)](https://langchain-ai.github.io/langgraph/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15+pgvector-4169E1?logo=postgresql&logoColor=white)](https://github.com/pgvector/pgvector)
[![Redis](https://img.shields.io/badge/Redis-7-DC382D?logo=redis&logoColor=white)](https://redis.io)
[![Kafka](https://img.shields.io/badge/Kafka-Confluent-231F20?logo=apache-kafka)](https://kafka.apache.org)
[![Docker](https://img.shields.io/badge/Docker-Compose_v2-2496ED?logo=docker&logoColor=white)](https://docs.docker.com/compose/)

NEXUS lets users submit a natural-language query and watch in real time as specialized AI agents — Search, Code, Memory, and Tool — collaborate to answer it. A LangGraph-powered Orchestrator decomposes the query, dispatches tasks, and synthesizes a final answer while streaming every thought to the browser via SSE.

---

## Live Demo

<iframe 
    width="800" 
    height="450"
    src="https://www.youtube.com/embed/BrcfatovUzE"
    frameborder="0"
    allowfullscreen>
</iframe>

---


## Architecture

```mermaid
graph TB
    subgraph Browser
        FE[Next.js 14<br/>App Router]
    end

    subgraph NGINX["NGINX :8080"]
        NX[Reverse Proxy]
    end

    subgraph Gateway["API Gateway :8000"]
        GW_AUTH[Auth Middleware<br/>JWT + Redis session]
        GW_RL[Rate Limit<br/>60 req/min]
        GW_RUNS["/api/v1/runs"]
        GW_SSE["/api/v1/sse"]
        GW_MEM["/api/v1/memory"]
        GW_METRICS["/api/v1/metrics"]
    end

    subgraph Orchestrator["Orchestrator :8001"]
        GRAPH[LangGraph<br/>StateGraph]
        subgraph Nodes
            DQ[decompose_query]
            VP[validate_plan]
            DT[dispatch_next_task]
            AR[await_task_result]
            RR[record_result]
            SO[synthesize_output]
            FR[finalize_run]
            HE[handle_error]
        end
        subgraph Agents["Internal Agent Modules"]
            SA[Search Agent<br/>Tavily/Mock]
            CA[Code Agent<br/>Python sandbox]
            MA[Memory Agent<br/>sentence-transformers]
            TA[Tool Agent<br/>calc/weather/wiki]
        end
        SSE_EMIT[sse_emitter.py<br/>Redis pub/sub]
    end

    subgraph Infra
        PG[(PostgreSQL 15<br/>+pgvector)]
        RD[(Redis 7<br/>sessions · rate-limit · SSE)]
        KF[[Kafka<br/>nexus.events]]
        JG[Jaeger<br/>Traces]
        PR[Prometheus<br/>Metrics]
    end

    FE -->|HTTP/SSE| NX
    NX -->|/api/*| GW_AUTH
    GW_AUTH --> GW_RL --> GW_RUNS
    GW_RUNS -->|POST /orchestrate| GRAPH
    GW_SSE -->|httpx stream| SSE_EMIT
    GRAPH --> DQ --> VP --> DT
    DT -->|direct call| SA
    DT -->|direct call| CA
    DT -->|direct call| MA
    DT -->|direct call| TA
    DT --> AR --> RR --> SO --> FR
    FR -->|UPDATE runs| PG
    DQ & VP & DT & RR & SO & FR -->|emit_event| RD
    SSE_EMIT -->|subscribe| RD
    GW_AUTH -->|session check| RD
    GW_RUNS -->|INSERT/SELECT| PG
    MA -->|INSERT vector| PG
    Nodes -->|Kafka events| KF
    Gateway -->|OTLP spans| JG
    Orchestrator -->|OTLP spans| JG

    Gateway -->|/metrics| PR
    Orchestrator -->|/metrics| PR
```

For a detailed prose description of each component, see [docs/architecture.md](docs/architecture.md).

### System Design

The system is split into two deployed services (see [ADR-005](docs/decisions/ADR-005-railway.md)):

- **API Gateway** (`services/gateway/`) — authentication, rate limiting, routing, SSE proxy
- **Orchestrator** (`services/orchestrator/`) — LangGraph state machine + all four agent implementations as internal Python modules

All four agents (Search, Code, Memory, Tool) live inside the Orchestrator process and are called as direct Python function calls from `nodes/dispatch_next_task.py`. This is a deliberate architectural trade-off documented in ADR-005.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | Next.js 14 App Router, TypeScript, TailwindCSS, SWR, Recharts |
| API Gateway | FastAPI 0.111, Python 3.11, asyncpg, SQLAlchemy 2.0 async |
| Orchestration | LangGraph 0.1, Anthropic Claude claude-sonnet-4-20250514 |
| Search Agent | Tavily API (mock fallback), Redis LLM cache |
| Code Agent | asyncio subprocess sandbox, Claude tool use |
| Memory Agent | sentence-transformers all-MiniLM-L6-v2, pgvector cosine ANN |
| Tool Agent | Claude function calling → calculator / open-meteo / Wikipedia |
| Database | PostgreSQL 15 + pgvector extension |
| Cache / Sessions | Redis 7 |
| Streaming | Server-Sent Events, Redis pub/sub |
| Message Queue | Apache Kafka (Confluent), aiokafka |
| Observability | OpenTelemetry + Jaeger, structlog JSON, Prometheus |
| Infrastructure | Docker Compose v2, NGINX reverse proxy |
| Deployment | Railway (backend), Vercel (frontend) |

---

## Quick Start

> **Prerequisites:** Docker Desktop 4.25+, Python 3.11 (pyenv), Node 20 (nvm), PowerShell 7 (Windows)

### 1 — Clone and configure

```powershell
git clone https://github.com/<your-handle>/nexus.git
cd nexus
Copy-Item .env.example .env
# Edit .env: set POSTGRES_PASSWORD, REDIS_PASSWORD, ANTHROPIC_API_KEY (or GEMINI_API_KEY), JWT_SECRET_KEY
notepad .env
```

### 2 — Start infrastructure

```powershell
.\scripts\start-infra.ps1
```

Starts PostgreSQL, Redis, Kafka, Zookeeper, NGINX, Jaeger, and Prometheus. Waits for all health checks to pass and creates Kafka topics.

### 3 — Seed the database

```powershell
Copy-Item db\.env.example db\.env
# Edit db\.env: set DATABASE_URL_LOCAL=postgresql+asyncpg://nexus:<password>@localhost:5434/nexus_db
notepad db\.env
.\scripts\seed-db.ps1
```

Inserts 10 users, 4 agent definitions, 50 runs, and 200 tasks.

### 4 — Start application services

```powershell
.\scripts\start-all-services.ps1
```

Builds and starts the Gateway (port 8000) and Orchestrator (port 8001).

### 5 — Start the frontend

```powershell
cd frontend
Copy-Item .env.local.example .env.local
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000). Register an account, submit a query, watch the thought trace.

---

## Architecture Decision Records

| ADR | Decision |
|---|---|
| [ADR-001](docs/decisions/ADR-001-langgraph.md) | LangGraph over CrewAI for agent orchestration |
| [ADR-002](docs/decisions/ADR-002-pgvector.md) | pgvector over Pinecone for vector storage |
| [ADR-003](docs/decisions/ADR-003-sse-vs-websocket.md) | SSE over WebSockets for real-time streaming |
| [ADR-004](docs/decisions/ADR-004-kafka-topics.md) | Kafka topic design (3 topics, partition strategy) |
| [ADR-005](docs/decisions/ADR-005-railway.md) | Railway deployment + microservices → hybrid monolith migration |

---

## Project Structure

```text
nexus/
├── services/
│   ├── _archived/        # All agents microservices (see ADR-005)
│   ├── gateway/          # API Gateway (FastAPI)
│   ├── orchestrator/     # Orchestrator + all agents (LangGraph + FastAPI)
│   │   └── agents/       # Search, Code, Memory, Tool agent modules
│   └── shared/           # Shared Python modules (logging, metrics, kafka)
├── frontend/             # Next.js 14 App Router
├── db/                   # PostgreSQL schema, migrations, seed script
├── infra/                # NGINX, Kafka, Prometheus configs
├── docs/
│   ├── architecture.md
│   └── decisions/        # ADR-001 through ADR-005
└── scripts/              # PowerShell automation (Windows)
```

---

## Running Tests

```powershell
.\scripts\test-all.ps1
```

Runs: infrastructure integration tests, DB schema tests (pytest-asyncio), gateway unit tests, orchestrator node unit tests.

---

## Screenshots

![alt text](<Screenshots/Screenshot 2026-05-27 091721.png>)
![alt text](<Screenshots/Screenshot 2026-05-27 091712.png>)
![alt text](<Screenshots/Screenshot 2026-05-27 084245.png>)
![alt text](<Screenshots/Screenshot 2026-05-27 084846.png>)
![alt text](<Screenshots/Screenshot 2026-05-27 085942.png>)
![alt text](<Screenshots/Screenshot 2026-05-27 085809.png>)
![alt text](<Screenshots/Screenshot 2026-05-27 085831.png>)
![alt text](<Screenshots/Screenshot 2026-05-27 085839.png>)



---

## License

MIT — see [LICENSE](LICENSE).