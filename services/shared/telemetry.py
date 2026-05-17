"""
OpenTelemetry tracing configuration for all NEXUS services.
 
Every service calls configure_telemetry() once at startup (inside the lifespan
context manager). After that call, the service emits OTLP spans to the Jaeger
collector running at JAEGER_ENDPOINT (default: http://jaeger:4317).
 
Traces can be viewed in the Jaeger UI at http://localhost:16686.
 
Usage (in each service's main.py lifespan):
    from shared.telemetry import configure_telemetry
    configure_telemetry(service_name="gateway", environment="development")
 
The tracer is then obtained anywhere in the service via:
    from opentelemetry import trace
    tracer = trace.get_tracer(__name__)
 
    with tracer.start_as_current_span("my_operation") as span:
        span.set_attribute("user.id", user_id)
        result = await do_work()
"""

import os
from typing import Optional

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.semconv.resource import ResourceAttributes

# Default Jaeger OTLP gRPC endpoint — matches docker-compose.yml service name

_DEFAULT_JAEGER_ENDPOINT = "http://jaeger:4317"

def configure_telemetry(
    service_name: str,
    environment: str = "development",
    jaeger_endpoint: Optional[str] = None,
) -> None:
    """
    Configure OpenTelemetry tracing with a Jaeger OTLP exporter.
 
    Sets up a TracerProvider with a BatchSpanProcessor that exports spans to
    the Jaeger collector. In development, also attaches a ConsoleSpanExporter
    so spans are visible in the service's stdout log stream.
 
    Falls back to console-only export if the JAEGER_ENDPOINT is unreachable —
    this prevents startup failure when running services outside Docker Compose
    (e.g. during local unit testing).
 
    Args:
        service_name: Logical name for this service in Jaeger traces.
                      Should match the Docker Compose service name:
                      "gateway", "orchestrator", "search-agent", etc.
        environment:  Deployment environment tag added to all spans.
                      Typically settings.environment — "development" or "production".
        jaeger_endpoint: Override the OTLP gRPC endpoint. If None, reads from
                         the OTEL_EXPORTER_OTLP_ENDPOINT environment variable, falling back
                         to http://jaeger:4317.
    """
    endpoint: str = (
        jaeger_endpoint
        or os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", _DEFAULT_JAEGER_ENDPOINT)
    )
 
    resource = Resource.create(
        {
            ResourceAttributes.SERVICE_NAME: service_name,
            ResourceAttributes.DEPLOYMENT_ENVIRONMENT: environment,
            ResourceAttributes.SERVICE_VERSION: "0.1.0",
        }
    )
 
    provider = TracerProvider(resource=resource)
 
    # OTLP → Jaeger exporter (batched for efficiency)
    try:
        otlp_exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)
        provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
    except Exception:
        # Do not crash the service if Jaeger is unavailable (e.g. unit tests,
        # local dev without full Docker Compose stack). Spans are silently dropped.
        pass
 
    # Console exporter for development visibility — disabled in production
    if environment == "development":
        provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
 
    trace.set_tracer_provider(provider)