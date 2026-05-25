"""
Prometheus custom metric definitions shared across all NEXUS services.

Every service imports the metric objects it needs directly from this module.
Metrics are registered with the default Prometheus registry on import —
prometheus-fastapi-instrumentator then exposes them at GET /metrics.

Usage:
    from shared.metrics import (
        llm_tokens_total,
        llm_request_duration_seconds,
        agent_task_duration_seconds,
        agent_errors_total,
        kafka_messages_produced_total,
        kafka_messages_consumed_total,
        sse_connections_active,
    )

    # Increment a counter
    llm_tokens_total.labels(service="gateway", model="claude-sonnet-4-20250514", type="input").inc(150)

    # Observe a histogram
    with agent_task_duration_seconds.labels(agent="search", status="success").time():
        result = await run_task()

All metric names follow the Prometheus convention:
  nexus_<subsystem>_<name>_<unit>
"""

from prometheus_client import Counter, Gauge, Histogram

# LLM / Anthropic API metrics

llm_tokens_total = Counter(
    name="nexus_llm_tokens_total",
    documentation="Total tokens consumed across all Anthropic API calls.",
    labelnames=["service", "model", "type"],  # type is "input" or "output"
)

llm_request_duration_seconds = Histogram(
    name="nexus_llm_request_duration_seconds",
    documentation="End-to-end latency of Anthropic API calls in seconds.",
    labelnames=["service", "model"],
    buckets=(0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 30.0, 60.0),
)

llm_requests_total = Counter(
    name="nexus_llm_requests_total",
    documentation="Total number of Anthropic API calls.",
    labelnames=["service", "model", "status"],  # status is "success" or "error" or "cached"
)

# Agent task metrics

agent_task_duration_seconds = Histogram(
    name="nexus_agent_task_duration_seconds",
    documentation="Time taken for an agent to complete a dispathed task.",
    labelnames=["agent", "status"],  # agent: "search"|"code"|"memory"|"tool""
    buckets=(0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 30.0, 60.0),
)

agent_errors_total = Counter(
    name="nexus_agent_errors_total",
    documentation="Total number of agent task errors by agent type and error class.",
    labelnames=["agent", "error_class"],
)

agent_tasks_total = Counter(
    name="nexus_agent_tasks_total",
    documentation="Total number of agents tasks dispatched.",
    labelnames=["agent", "status"],
)

# Orchestrator / run metrics

orchestrator_runs_total = Counter(
    name="nexus_orchestrator_runs_total",
    documentation="Total number of orchestrator runs started.",
    labelnames=["status"],
)

orchestrator_run_duration_seconds = Histogram(
    name="nexus_orchestrator_run_duration_seconds",
    documentation="End-to-end wall-clock time for a complete orchestration run.",
    labelnames=["status"],
    buckets=(1.0, 5.0, 10.0, 20.0, 30.0, 60.0, 120.0, 300.0),
)

active_runs = Gauge(
    name="nexus_active_runs",
    documentation="Number of orchestration runs currently in flight.",
    labelnames=["service"],
)

# Kafka metrics

kafka_messages_produced_total = Counter(
    name="nexus_kafka_messages_produced_total",
    documentation="Total number of messages produced, by topic.",
    labelnames=["topic", "service"],
)

kafka_messages_consumed_total = Counter(
    name="nexus_kafka_messages_consumed_total",
    documentation="Total number of messages consumed, by topic and consumer group.",
    labelnames=["topic", "group", "service"],
)

kafka_produce_errors_total = Counter(
    name="nexus_kafka_produce_errors_total",
    documentation="Total Kafka produce failures, by topic",
    labelnames=["topic", "service"],
)

# SSE / streaming metrics

sse_connections_active = Gauge(
    name="nexus_sse_connections_active",
    documentation="Number of currently open SSE streaming connections.",
    labelnames=["service"],
)

sse_events_emitted_total = Counter(
    name="nexus_sse_events_emitted_total",
    documentation="Total SSE events emitted to clients, by event type.",
    labelnames=["service", "event_type"],
)

# Redis cache metrics

redis_cache_hits_total = Counter(
    name="nexus_redis_cache_hits_total",
    documentation="Total Redis cache hits for Claude response caching.",
    labelnames=["service"],
)

redis_cache_misses_total = Counter(
    name="nexus_redis_cache_misses_total",
    documentation="Total Redis cache misses for Claude response caching.",
    labelnames=["service"],
)


def configure_metrics() -> None:
    """
    No-op initialiser kept for API symmetry with configure_logging/configure_telemetry.

    All metrics self-register with the default Prometheus registry on import.
    Call this in the service lifespan to make the import side-effects explicit
    and searchable in the codebase.
    """
    # Metrics are registered on import via module-level declarations above.
    # This function exists so every service's main.py lifespan reads uniformly:
    #   configure_logging(...)
    #   configure_telemetry(...)
    #   configure_metrics()
    pass
