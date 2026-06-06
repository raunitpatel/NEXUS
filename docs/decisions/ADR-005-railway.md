# ADR-005: Deployment Notes for the Learning Topology

**Status:** Accepted  
**Date:** 2025-05  
**Deciders:** NEXUS engineering

---

## Context

This branch is kept for learning the full distributed shape of NEXUS. The local topology runs separate application services for the Gateway, Orchestrator, Search Agent, Code Agent, Memory Agent, and Tool Agent, plus infrastructure containers for PostgreSQL, Redis, Kafka, NGINX, Jaeger, and Prometheus.

Railway and Vercel are still useful deployment targets to understand managed hosting constraints, environment variables, health checks, and service-to-service networking.

## Decision

Keep the local development topology as separate services and document Railway/Vercel deployment as an exercise in operational constraints rather than changing the service boundaries in this branch.

## Consequences

**Positive:**
- Service boundaries stay explicit for learning HTTP dispatch, health checks, tracing, and failure handling.
- Each agent can be inspected, run, and tested independently.
- The architecture remains close to the distributed mental model shown in README Mermaid diagrams.

**Negative:**
- More containers and environment files must be managed locally.
- Railway deployment requires careful service configuration, private networking, and per-service health checks.
- Kafka, Jaeger, and Prometheus add local resource cost even when only part of the stack is being studied.

## Implementation

- `scripts/start-infra.ps1` starts shared infrastructure.
- `scripts/start-all-services.ps1` starts Gateway, Orchestrator, and the four agent services.
- The frontend can run separately with `npm run dev` from `frontend/`.
- Railway deployment should map each backend service to its own configured service when practicing deployment from this branch.
