## `docs/api.md` — NEXUS API Reference

```markdown
# NEXUS API Reference

Base URL (local): `http://localhost:8080`  
Base URL (production): `https://<your-railway-gateway>.railway.app`

All endpoints except `/api/v1/auth/*` and `/healthz` require a valid JWT Bearer token.

---

## Authentication

### Headers

```
Authorization: Bearer <access_token>
```

The token is obtained from `POST /api/v1/auth/login`. It is a signed HS256 JWT with a 24-hour expiry. Server-side session validation is performed on every request via a Redis `session:{jti}` key — tokens can be revoked server-side by deleting the key.

---

## Endpoints

### Auth

#### `POST /api/v1/auth/register`

Create a new user account.

**Request body**

```json
{
  "email": "user@example.com",
  "password": "MyPassword1!",
  "display_name": "Aryan Kumar"
}
```

| Field | Type | Required | Constraints |
|---|---|---|---|
| `email` | string | Yes | Valid email, max 320 chars |
| `password` | string | Yes | 8–128 chars |
| `display_name` | string | No | Max 100 chars |

**Response `201 Created`**

```json
{
  "user_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "email": "user@example.com",
  "display_name": "Aryan Kumar"
}
```

**Errors**

| Status | Condition |
|---|---|
| `409 Conflict` | Email already registered |
| `422 Unprocessable Entity` | Validation failure (password too short, invalid email) |

---

#### `POST /api/v1/auth/login`

Exchange credentials for a JWT access token.

**Request body**

```json
{
  "email": "user@example.com",
  "password": "MyPassword1!"
}
```

**Response `200 OK`**

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 86400
}
```

**Errors**

| Status | Condition |
|---|---|
| `401 Unauthorized` | Invalid email or password |
| `503 Service Unavailable` | Redis session write failed |

---

### Runs

All run endpoints scope data to the authenticated user. Users can never read or enumerate other users' runs.

#### `POST /api/v1/runs`

Create a new agent orchestration run.

**Request body**

```json
{
  "query": "Research the latest papers on diffusion models and write a Python snippet to load one."
}
```

| Field | Type | Required | Constraints |
|---|---|---|---|
| `query` | string | Yes | 1–4096 chars, non-empty after trim |

**Response `201 Created`**

```json
{
  "run_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "status": "running"
}
```

The run is created synchronously and dispatched to the Orchestrator asynchronously. The response returns immediately — poll `GET /api/v1/runs/{run_id}` or open an SSE stream to track progress.

**Errors**

| Status | Condition |
|---|---|
| `422 Unprocessable Entity` | Query is empty or exceeds 4096 chars |
| `503 Service Unavailable` | Orchestrator unreachable (run row still created in DB) |

---

#### `GET /api/v1/runs`

List runs for the authenticated user, newest first.

**Query parameters**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `limit` | integer | `50` | Max results (1–200) |
| `offset` | integer | `0` | Pagination offset |
| `page` | integer | — | If provided, activates paginated response format |
| `size` | integer | — | Page size (1–200); used with `page` |
| `status` | string | — | Filter: `pending`, `running`, `completed`, `failed`, `cancelled` |
| `start_date` | string | — | ISO date filter: runs created on or after this date |
| `end_date` | string | — | ISO date filter: runs created before this date + 1 day |

**Response `200 OK` — simple list (no `page` param)**

```json
[
  {
    "run_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "status": "completed",
    "query": "What is the capital of France?",
    "created_at": "2025-01-15T10:30:00.000000+00:00",
    "duration_seconds": 12,
    "agents_used": ["Search Agent", "Tool Agent"],
    "input_tokens": 850,
    "output_tokens": 420,
    "total_tokens": 1270,
    "latency_ms": 12340.0
  }
]
```

**Response `200 OK` — paginated (with `page` param)**

```json
{
  "runs": [...],
  "total_count": 47,
  "page": 1,
  "size": 20
}
```

**Run object fields**

| Field | Type | Description |
|---|---|---|
| `run_id` | string (UUID) | Unique run identifier |
| `status` | string | `pending` \| `running` \| `completed` \| `failed` \| `cancelled` |
| `query` | string | Original user query (truncated to 200 chars in list view) |
| `created_at` | string (ISO 8601) | UTC timestamp |
| `duration_seconds` | integer \| null | Wall-clock seconds from creation to completion |
| `agents_used` | string[] | Agent display names that executed tasks for this run |
| `input_tokens` | integer | Total LLM input tokens |
| `output_tokens` | integer | Total LLM output tokens |
| `total_tokens` | integer | Sum of input + output tokens |
| `latency_ms` | number \| null | End-to-end latency in milliseconds |

---

#### `GET /api/v1/runs/{run_id}`

Get a single run by ID.

**Path parameters**

| Parameter | Type | Description |
|---|---|---|
| `run_id` | string (UUID) | Run identifier |

**Response `200 OK`** — same shape as a single element in the list response above.

**Errors**

| Status | Condition |
|---|---|
| `404 Not Found` | Run does not exist or belongs to a different user |

Note: 404 is returned for both "not found" and "belongs to another user" — this prevents run ID enumeration.

---

#### `GET /api/v1/runs/{run_id}/events`

List persisted thought-trace events for a run.

Used by the run detail page for completed and failed runs, after the short-lived Redis SSE replay buffer (60s TTL) has expired.

**Query parameters**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `limit` | integer | `200` | Max events (1–500) |

**Response `200 OK`**

```json
[
  {
    "event_id": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
    "run_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "task_id": "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
    "event_type": "thought",
    "source": "orchestrator.decompose_query",
    "payload": {
      "content": "Decomposed into 2 task(s): search, tool"
    },
    "created_at": "2025-01-15T10:30:01.000000+00:00"
  }
]
```

**Event object fields**

| Field | Type | Description |
|---|---|---|
| `event_id` | string (UUID) | Unique event identifier |
| `run_id` | string (UUID) | Parent run |
| `task_id` | string (UUID) \| null | Associated task, if any |
| `event_type` | string | See event types table below |
| `source` | string | Dotted identifier of the emitting node (e.g. `orchestrator.decompose_query`) |
| `payload` | object | Arbitrary JSON data specific to the event type |
| `created_at` | string (ISO 8601) | UTC timestamp |

**Event types**

| `event_type` | Emitted by | Payload keys |
|---|---|---|
| `run_start` | `decompose_query` | `query` |
| `thought` | `decompose_query`, `synthesize_output` | `content` |
| `orchestrator_plan` | `decompose_query` | `task_count`, `agent_types` |
| `orchestrator_dispatch` | `dispatch_next_task` | `task_id`, `agent_type`, `dispatch_mode` |
| `agent_start` | each agent | `instruction` or `query`, `agent` |
| `agent_end` | each agent | full result dict |
| `tool_call` | `tool_agent` | `tool_name`, `input` |
| `tool_result` | `record_result` | `task_id`, `agent_type`, `status`, `duration_ms`, `output`, `summary` |
| `code_iteration` | `code_agent` | `iteration`, `code`, `exit_code`, `stdout`, `stderr` |
| `memory_read` | `memory_agent` | `query`, `result_count` |
| `memory_write` | `memory_agent` | `content`, `embedding_id` |
| `llm_response` | `synthesize_output` | `content` |
| `orchestrator_synthesize` | `synthesize_output` | `content` |
| `run_complete` | `finalize_run` | `status`, `output`, `completed_tasks`, `input_tokens`, `output_tokens`, `duration_ms` |
| `run_error` | `handle_error`, `finalize_run` | `error`, `retry_count` |

**Errors**

| Status | Condition |
|---|---|
| `404 Not Found` | Run does not exist or belongs to a different user |

---

### SSE (Real-Time Streaming)

#### `GET /api/v1/sse/{run_id}?token=<jwt>`

Open a Server-Sent Events stream for a run.

Authentication uses the `?token=` query parameter because the browser `EventSource` API does not support custom request headers.

**Query parameters**

| Parameter | Type | Required | Description |
|---|---|---|---|
| `token` | string | Yes | JWT access token (same value as the Bearer token) |

**Response `200 OK`**

Content-Type: `text/event-stream`

The stream yields W3C SSE-formatted events:

```
: stream-open run_id=3fa85f64-5717-4562-b3fc-2c963f66afa6

event: run_start
data: {"event_type":"run_start","payload":{"query":"..."},"run_id":"...","timestamp":1705312201.0}
id: 1

event: thought
data: {"event_type":"thought","payload":{"content":"Decomposed into 2 task(s): search, tool"},...}
id: 2

event: orchestrator_dispatch
data: {"event_type":"orchestrator_dispatch","payload":{"task_id":"...","agent_type":"search"},...}
id: 3

...

event: run_complete
data: {"event_type":"run_complete","payload":{"status":"completed","output":"The answer is..."},...}
id: 12

```

The stream closes automatically after receiving `run_complete` or `run_error`.

**Heartbeat:** A `: heartbeat` comment is sent every 15 seconds when no events arrive, keeping the connection alive through proxies.

**Late-join replay:** If the run has already completed when the client connects, the Gateway checks the Redis `sse:done:{run_id}` sentinel. If set, it replays all buffered events from `sse:events:{run_id}` (60-second TTL list) and closes the stream immediately.

**Errors**

| Status | Condition |
|---|---|
| `401 Unauthorized` | Missing, expired, or revoked token |
| `403 Forbidden` | Token belongs to a different user than the run owner |
| `404 Not Found` | Run does not exist |
| `422 Unprocessable Entity` | `token` query parameter missing |

**Frontend usage**

```typescript
// frontend/hooks/useSSEStream.ts
const url = `${BASE_URL}/api/v1/sse/${runId}?token=${encodeURIComponent(token)}`
const es = new EventSource(url)
es.onmessage = (event) => { /* handle event */ }
```

---

### Agents

#### `GET /api/v1/agents`

List all registered agents with live health status.

Health checks (`GET /healthz` on each agent's `base_url`) are fired concurrently with a 3-second timeout.

**Response `200 OK`**

```json
[
  {
    "agent_id": "00000000-0000-0000-0000-000000000001",
    "name": "Search Agent",
    "type": "search",
    "base_url": "http://search-agent:8002",
    "description": "Formulates queries, retrieves web results, summarises sources.",
    "is_active": true,
    "is_healthy": true
  },
  {
    "agent_id": "00000000-0000-0000-0000-000000000002",
    "name": "Code Agent",
    "type": "code",
    "base_url": "http://code-agent:8003",
    "description": "Writes, debugs, and executes Python code in a sandboxed subprocess.",
    "is_active": true,
    "is_healthy": null
  }
]
```

| Field | Type | Description |
|---|---|---|
| `agent_id` | string (UUID) | Stable UUID seeded by `db/seed.py` |
| `name` | string | Display name |
| `type` | string | `search` \| `code` \| `memory` \| `tool` \| `orchestrator` |
| `base_url` | string | Internal Docker service URL |
| `description` | string \| null | Human-readable description |
| `is_active` | boolean | Whether enabled in the DB |
| `is_healthy` | boolean \| null | Live `/healthz` result; `null` if agent is inactive |

---

#### `GET /api/v1/agents/{agent_id}`

Get a single agent by ID with live health status.

**Response `200 OK`** — same shape as a single element from the list above.

**Errors**

| Status | Condition |
|---|---|
| `404 Not Found` | Agent not found |

---

### Memory

#### `GET /api/v1/memory`

List recent memory embeddings for the authenticated user, newest first.

Proxied to `GET /memory` on the Orchestrator with `x-user-id` header.

**Query parameters**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `limit` | integer | `20` | Max results (1–100) |
| `offset` | integer | `0` | Pagination offset |

**Response `200 OK`**

```json
[
  {
    "embedding_id": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
    "run_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "content": "Chain-of-thought prompting significantly improves LLM reasoning on multi-step tasks...",
    "model": "all-MiniLM-L6-v2",
    "created_at": "2025-01-15T10:30:00.000000+00:00"
  }
]
```

---

#### `GET /api/v1/memory/search`

Semantic similarity search over the authenticated user's stored embeddings.

Proxied to `GET /memory/search` on the Orchestrator. Results are cached in Redis for 5 minutes per `(user_id, query)` pair.

**Query parameters**

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `q` | string | Yes | — | Search query (1–500 chars) |
| `limit` | integer | No | `10` | Max results (1–50) |
| `similarity_threshold` | float | No | `0.35` | Minimum cosine similarity (0.0–1.0) |

**Response `200 OK`**

```json
{
  "query": "diffusion models Python",
  "results": [
    {
      "embedding_id": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
      "run_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
      "content": "Diffusion models use iterative denoising to generate images...",
      "similarity": 0.87,
      "model": "all-MiniLM-L6-v2",
      "created_at": "2025-01-15T10:30:00.000000+00:00"
    }
  ],
  "from_cache": false,
  "duration_ms": 43
}
```

| Field | Type | Description |
|---|---|---|
| `query` | string | Echo of the input query |
| `results` | array | Ordered by similarity descending |
| `results[].similarity` | float | Cosine similarity score (0.0–1.0) |
| `from_cache` | boolean | True if served from Redis cache |
| `duration_ms` | integer | Total search duration including embedding encode time |

**Errors**

| Status | Condition |
|---|---|
| `503 Service Unavailable` | Orchestrator unreachable or timed out |

---

### Metrics

All metrics endpoints are scoped to the authenticated user. Users see only their own data.

#### `GET /api/v1/metrics/summary`

Overall run statistics for the authenticated user.

**Query parameters**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `days` | integer | `7` | Lookback window for token/latency stats (1–90) |

**Response `200 OK`**

```json
{
  "total_runs": 47,
  "successful_runs": 38,
  "failed_runs": 5,
  "success_rate": 0.8085,
  "total_input_tokens": 142000,
  "total_output_tokens": 68500,
  "avg_run_duration_ms": 8340.5,
  "active_runs": 1,
  "period_days": 7
}
```

| Field | Description |
|---|---|
| `total_runs` | All-time run count |
| `successful_runs` | Runs with `status = 'completed'` (all-time) |
| `failed_runs` | Runs with `status = 'failed'` (all-time) |
| `success_rate` | `successful_runs / total_runs` as 0.0–1.0 |
| `total_input_tokens` | Sum of LLM input tokens within the `days` window |
| `total_output_tokens` | Sum of LLM output tokens within the `days` window |
| `avg_run_duration_ms` | Average `duration_ms` from run metadata within the `days` window |
| `active_runs` | Runs currently with `status = 'running'` |
| `period_days` | Echoed `days` parameter |

---

#### `GET /api/v1/metrics/agent-stats`

Per-agent task breakdown for the authenticated user.

**Query parameters**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `days` | integer | `7` | Lookback window (1–90) |

**Response `200 OK`**

```json
[
  {
    "agent_type": "search",
    "total_tasks": 28,
    "successful_tasks": 25,
    "failed_tasks": 2,
    "success_rate": 0.8929,
    "avg_duration_ms": 4120.5
  },
  {
    "agent_type": "tool",
    "total_tasks": 14,
    "successful_tasks": 14,
    "failed_tasks": 0,
    "success_rate": 1.0,
    "avg_duration_ms": 1830.0
  }
]
```

`agent_type` values: `search`, `code`, `memory_read`, `memory_write`, `tool`

---

#### `GET /api/v1/metrics/token-usage`

Daily LLM token consumption for the past N days.

**Query parameters**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `days` | integer | `7` | Number of calendar days (1–90) |

**Response `200 OK`**

```json
[
  {
    "date": "2025-01-15",
    "input_tokens": 24500,
    "output_tokens": 11200,
    "run_count": 8
  },
  {
    "date": "2025-01-16",
    "input_tokens": 18300,
    "output_tokens": 9100,
    "run_count": 6
  }
]
```

Days with no completed runs are omitted. Ordered by date ascending.

---

#### `GET /api/v1/metrics/latency`

Daily average and p95 run latency for the past N days.

**Query parameters**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `days` | integer | `7` | Number of calendar days (1–90) |

**Response `200 OK`**

```json
[
  {
    "date": "2025-01-15",
    "avg_duration_ms": 7840.0,
    "p95_duration_ms": 14200.0,
    "run_count": 8
  }
]
```

Latency is derived from the `duration_ms` key in `runs.metadata`. Rows with no `duration_ms` value are excluded. `p95_duration_ms` uses PostgreSQL `PERCENTILE_CONT(0.95)`.

---

### Health

#### `GET /healthz`

Liveness probe. No authentication required.

**Response `200 OK`**

```json
{
  "status": "ok"
}
```

Used by Docker Compose health checks and Railway deployment health checks.

---

## Rate Limiting

All authenticated endpoints are rate-limited at **60 requests per minute** per user, using a Redis fixed-window counter. The window resets at the start of each UTC minute.

Response headers on every non-429 response:

| Header | Value |
|---|---|
| `X-RateLimit-Limit` | `60` |
| `X-RateLimit-Remaining` | Requests remaining in the current window |

On limit exceeded:

**`429 Too Many Requests`**

```json
{
  "detail": "Rate limit exceeded. Try again in a moment."
}
```

| Header | Value |
|---|---|
| `X-RateLimit-Limit` | `60` |
| `X-RateLimit-Remaining` | `0` |
| `Retry-After` | Seconds until the next window opens |

If Redis is unavailable, the rate limiter **fails open** — requests pass through without limiting.

---

## Error Response Format

All errors follow FastAPI's default format:

```json
{
  "detail": "Human-readable error description"
}
```

For validation errors (`422`):

```json
{
  "detail": [
    {
      "type": "string_too_short",
      "loc": ["body", "query"],
      "msg": "String should have at least 1 character",
      "input": "",
      "ctx": {"min_length": 1}
    }
  ]
}
```

---

## Pagination

Two pagination styles are supported on `GET /api/v1/runs`:

**Offset-based** (default, used by Dashboard):
```
GET /api/v1/runs?limit=10&offset=0
```
Returns a plain JSON array.

**Page-based** (used by History page):
```
GET /api/v1/runs?page=2&size=20
```
Returns a `RunListResponse` object with `runs`, `total_count`, `page`, `size`.

If both `page` and `offset` are provided, `page`-based wins.

---

## Frontend Integration

The frontend accesses all endpoints through `frontend/lib/api.ts`:

```typescript
// All API calls go through apiFetch — never call fetch() directly
import { apiFetch } from '@/lib/api'

const runs = await apiFetch<Run[]>('/api/v1/runs?limit=10')
const run  = await apiFetch<CreateRunResponse>('/api/v1/runs', {
  method: 'POST',
  body: { query: 'Research transformers' },
})
```

`apiFetch` automatically injects the JWT Bearer token, serializes JSON bodies, handles 401 redirects to `/login`, and throws typed `ApiError` on non-2xx responses.

SSE connections are managed exclusively through `frontend/hooks/useSSEStream.ts` using the native `EventSource` API.
```