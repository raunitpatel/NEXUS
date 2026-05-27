# ADR-003: Use SSE for Real-Time Thought Trace Streaming

**Status:** Accepted  
**Date:** 2025-05
**Deciders:** NEXUS engineering

---

## Context

NEXUS streams live thought-trace events from the Orchestrator to the browser as an agent run executes. Events are unidirectional: server → client. The frontend displays each event as it arrives, building a live timeline.

Two options were evaluated: WebSockets and Server-Sent Events (SSE).

## Decision

Use **Server-Sent Events** via the browser's native `EventSource` API and FastAPI's `StreamingResponse`.

## Alternatives Considered

### WebSockets

WebSockets provide full-duplex communication. For NEXUS's use case this is unnecessary — the client never sends messages after the stream opens. WebSockets add complexity:
- Requires a WebSocket server (`websockets` or `starlette.websockets`) separate from HTTP routing
- Connection lifecycle is more complex (ping/pong, reconnect logic)
- NGINX proxy requires `Upgrade: websocket` header configuration
- Railway's HTTP proxy layer has historically had issues with long-lived WebSocket connections

### Long Polling

Long polling is simple but creates a thundering herd on reconnect and adds per-poll DB query overhead. Not suitable for sub-second event delivery.

## Consequences

**Positive:**
- SSE runs over standard HTTP — no protocol upgrade, no NGINX special configuration beyond `proxy_buffering off`
- `EventSource` reconnects automatically on disconnect
- NEXUS events are always server → client; SSE matches the communication pattern exactly
- Simpler: `StreamingResponse` in FastAPI, native `EventSource` in the browser
- HTTP/2 multiplexes SSE streams over a single TCP connection

**Negative:**
- SSE is unidirectional — if the frontend ever needs to send data mid-stream (e.g. cancel a run), a separate REST call is required
- Maximum 6 concurrent `EventSource` connections per domain in HTTP/1.1 (HTTP/2 removes this limit)
- `?token=JWT` query parameter is required because `EventSource` does not support custom request headers

## Implementation

- `services/orchestrator/sse_emitter.py` — `emit_event()` publishes to Redis pub/sub; `sse_stream_generator()` yields W3C SSE chunks
- `services/orchestrator/routers/sse.py` — `GET /runs/{run_id}/stream`
- `services/gateway/routers/sse.py` — `GET /api/v1/sse/{run_id}` proxies via httpx streaming
- `frontend/hooks/useSSEStream.ts` — manages `EventSource` lifecycle