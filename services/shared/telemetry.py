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

import logging
import os
from typing import Optional

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.propagate import set_global_textmap
from opentelemetry.propagators.b3 import B3MultiFormat
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.semconv.resource import ResourceAttributes

from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

# W3C Trace Context propagator — injects traceparent header into outgoing HTTP requests
from opentelemetry.propagators.composite import CompositePropagator
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

_DEFAULT_JAEGER_ENDPOINT = "http://jaeger:4317"

logger = logging.getLogger(__name__)


def configure_telemetry(
    service_name: str,
    environment: str = "development",
    jaeger_endpoint: Optional[str] = None,
    app: Optional[object] = None,
) -> None:
    """
    Configure OpenTelemetry tracing with a Jaeger OTLP exporter.
 
    Sets up a TracerProvider with BatchSpanProcessor → OTLPSpanExporter.
    Registers W3CTraceContextPropagator as the global propagator so that
    outgoing httpx requests automatically carry 'traceparent' headers.
    Instruments FastAPI (if app is provided) and asyncpg (if installed).
 
    Falls back gracefully if Jaeger is unreachable — service always starts.
 
    Args:
        service_name: Logical name for this service in Jaeger (e.g. "gateway").
        environment: Deployment environment tag ("development" or "production").
        jaeger_endpoint: Override OTLP gRPC endpoint. Reads OTEL_EXPORTER_OTLP_ENDPOINT
                         env var or falls back to http://jaeger:4317.
        app: FastAPI application instance. If provided, FastAPIInstrumentor is
             applied to auto-instrument all routes. Pass app after it is created.
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
        logger.info(
            "telemetry.otlp_exporter_configured",
            extra={"endpoint": endpoint, "service": service_name},
        )
    except Exception as exc:
        logger.warning(
            "telemetry.jaeger_unavailable",
            extra={"endpoint": endpoint, "error": str(exc)},
        )

    # Console exporter for development visibility — disabled in production
    # if environment == "development":
    #     provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))

    trace.set_tracer_provider(provider)

    # --- AGNT-016: added below ---
    # Set W3C Trace Context as global propagator so outgoing httpx requests
    # and incoming FastAPI requests share the same trace_id automatically.
    set_global_textmap(
        CompositePropagator([
            TraceContextTextMapPropagator(),  # W3C traceparent / tracestate
            B3MultiFormat(),                   # B3 headers for legacy systems
        ])
    )

    # Instrument asyncpg — creates DB query child spans automatically.
    # Wrapped in try/except because not all services use asyncpg directly
    # (some use SQLAlchemy async which has its own instrumentor).
    try:
        from opentelemetry.instrumentation.asyncpg import AsyncPGInstrumentor
        AsyncPGInstrumentor().instrument()
        logger.info("telemetry.asyncpg_instrumented", extra={"service": service_name})
    except ImportError:
        logger.debug(
            "telemetry.asyncpg_instrumentor_not_installed",
            extra={"service": service_name},
        )
    except Exception as exc:
        logger.warning(
            "telemetry.asyncpg_instrument_failed",
            extra={"service": service_name, "error": str(exc)},
        )

    # Instrument httpx — propagates traceparent into all outgoing HTTP calls
    # including dispatch_next_task.py calls to agent services.
    try:
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
        HTTPXClientInstrumentor().instrument()
        logger.info("telemetry.httpx_instrumented", extra={"service": service_name})
    except ImportError:
        logger.debug(
            "telemetry.httpx_instrumentor_not_installed",
            extra={"service": service_name},
        )
    except Exception as exc:
        logger.warning(
            "telemetry.httpx_instrument_failed",
            extra={"service": service_name, "error": str(exc)},
        )

    # Instrument FastAPI app if provided.
    # Called after app creation in each service's create_app() function.
    if app is not None:
        _instrument_fastapi(app, service_name)

    logger.info(
        "telemetry.configured",
        extra={"service": service_name, "environment": environment},
    )


def _instrument_fastapi(app: object, service_name: str) -> None:
    """
    Apply FastAPIInstrumentor to the given app instance.

    Creates HTTP server spans for every route handler. Span names follow
    the pattern '{HTTP_METHOD} {route_template}' (e.g. 'POST /api/v1/runs').
    Span attributes include http.method, http.url, http.status_code.

    Args:
        app: FastAPI application instance.
        service_name: Used in log messages for diagnostics.
    """
    try:
        FastAPIInstrumentor.instrument_app(app)  # type: ignore[arg-type]
        logger.info("telemetry.fastapi_instrumented", extra={"service": service_name})
    except ImportError:
        logger.warning(
            "telemetry.fastapi_instrumentor_not_installed",
            extra={"service": service_name},
        )
    except Exception as exc:
        logger.warning(
            "telemetry.fastapi_instrument_failed",
            extra={"service": service_name, "error": str(exc)},
        )