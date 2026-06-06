# ADR-004: Kafka Topic Design

**Status:** Accepted (runtime note below)  
**Date:** 2025-05
**Deciders:** NEXUS engineering

---

## Context

NEXUS keeps standalone Gateway, Orchestrator, Search, Code, Memory, and Tool services for learning distributed systems concepts. Kafka topics were designed for asynchronous task dispatch, task results, and event fan-out:

- `nexus.tasks` — orchestrator → agent dispatch
- `nexus.results` — agent → orchestrator results
- `nexus.events` — all services → SSE emitter / event log

**Runtime note:** The current learning branch dispatches agent work over HTTP from `dispatch_next_task.py`. `nexus.tasks` and `nexus.results` remain useful for schema practice and future async-dispatch experiments. `nexus.events` remains the active event topic.

## Decision

Three topics with the following characteristics (defined in `infra/kafka/create_topics.sh`):

| Topic | Partitions | Retention | Max message |
|---|---|---|---|
| `nexus.tasks` | 4 | 10 days | 1 MB |
| `nexus.results` | 4 | 10 days | 1 MB |
| `nexus.events` | 1 | 1 hour | 512 KB |

## Rationale

### Partition count

`nexus.tasks` and `nexus.results` use 4 partitions — one per agent type (search, code, memory, tool). This enables per-agent-type consumer groups with guaranteed ordering within an agent type. `nexus.events` uses 1 partition because SSE delivery is per-run and strict ordering within a run is required.

### Retention

Tasks and results are retained for 10 days to enable replay and debugging. Events are retained for 1 hour — they're ephemeral SSE payloads that become stale quickly.

### Message schemas

All messages are validated with Pydantic v2 models in `services/shared/kafka_schemas.py`:
- `TaskDispatchedMessage` — written to `nexus.tasks`
- `TaskResultMessage` — written to `nexus.results`
- `EventMessage` — written to `nexus.events`

## Consequences

**Positive:**
- Topic separation allows independent scaling of task dispatch and event streaming
- `nexus.events` single partition guarantees event ordering per run
- Pydantic schemas enforce message contracts at produce and consume time

**Negative:**
- `nexus.tasks` and `nexus.results` are provisioned but not part of the current HTTP dispatch path, consuming broker resources
- Kafka adds significant operational overhead (Zookeeper, broker JVM heap, topic management) for what is currently only used for SSE event publishing
- On Railway free tier, Kafka is not deployed — all Kafka publish calls fail silently (wrapped in try/except)

## Implementation

- `infra/kafka/create_topics.sh` — topic creation script executed by `scripts/start-infra.ps1`
- `services/shared/kafka_schemas.py` — Pydantic message schemas
- `services/shared/kafka_client.py` — `KafkaProducerFactory`, `KafkaConsumerFactory`
