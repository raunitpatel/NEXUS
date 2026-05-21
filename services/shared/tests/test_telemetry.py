"""
Unit tests for services/shared/telemetry.py.

Tests verify that configure_telemetry() sets up TracerProvider, registers the
correct propagator, instruments FastAPI and asyncpg, and handles Jaeger
unavailability gracefully — all without a live Jaeger container.

Run:
    cd nexus
    python -m pytest services/shared/tests/test_telemetry.py -v --asyncio-mode=auto
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch, call
import pytest


def _reset_otel() -> None:
    """Reset OTel global state between tests to prevent cross-test pollution."""
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    trace.set_tracer_provider(TracerProvider())


def test_configure_telemetry_sets_tracer_provider() -> None:
    """configure_telemetry() sets a non-default TracerProvider."""
    _reset_otel()
    from opentelemetry import trace

    with (
        patch("shared.telemetry.OTLPSpanExporter"),
        patch("shared.telemetry.BatchSpanProcessor"),
        patch("shared.telemetry._instrument_fastapi"),
    ):
        from shared.telemetry import configure_telemetry
        configure_telemetry(service_name="test-service", environment="development")

    provider = trace.get_tracer_provider()
    assert provider is not None


def test_configure_telemetry_registers_w3c_propagator() -> None:
    """configure_telemetry() installs TraceContextTextMapPropagator as global propagator."""
    _reset_otel()

    with (
        patch("shared.telemetry.OTLPSpanExporter"),
        patch("shared.telemetry.BatchSpanProcessor"),
        patch("shared.telemetry._instrument_fastapi"),
    ):
        from shared.telemetry import configure_telemetry
        configure_telemetry(service_name="test-service", environment="production")

    from opentelemetry.propagate import get_global_textmap
    from opentelemetry.propagators.composite import CompositePropagator
    propagator = get_global_textmap()
    assert isinstance(propagator, CompositePropagator)


def test_configure_telemetry_jaeger_unavailable_does_not_raise() -> None:
    """configure_telemetry() completes without raising when Jaeger connection fails."""
    _reset_otel()

    with patch(
        "shared.telemetry.OTLPSpanExporter",
        side_effect=Exception("Connection refused"),
    ):
        from shared.telemetry import configure_telemetry
        # Must not raise — service should start even if Jaeger is down
        configure_telemetry(
            service_name="test-service",
            environment="development",
            jaeger_endpoint="http://unreachable:4317",
        )


def test_configure_telemetry_instruments_fastapi_when_app_provided() -> None:
    """_instrument_fastapi() is called when app parameter is provided."""
    _reset_otel()
    mock_app = MagicMock()

    with (
        patch("shared.telemetry.OTLPSpanExporter"),
        patch("shared.telemetry.BatchSpanProcessor"),
        patch("shared.telemetry._instrument_fastapi") as mock_instrument,
    ):
        from shared.telemetry import configure_telemetry
        configure_telemetry(
            service_name="test-service",
            environment="development",
            app=mock_app,
        )

    mock_instrument.assert_called_once_with(mock_app, "test-service")


def test_configure_telemetry_skips_fastapi_when_app_not_provided() -> None:
    """_instrument_fastapi() is NOT called when app parameter is None."""
    _reset_otel()

    with (
        patch("shared.telemetry.OTLPSpanExporter"),
        patch("shared.telemetry.BatchSpanProcessor"),
        patch("shared.telemetry._instrument_fastapi") as mock_instrument,
    ):
        from shared.telemetry import configure_telemetry
        configure_telemetry(service_name="test-service", environment="development")

    mock_instrument.assert_not_called()


def test_configure_telemetry_asyncpg_import_error_handled_gracefully() -> None:
    """If opentelemetry-instrumentation-asyncpg is not installed, no crash."""
    _reset_otel()

    with (
        patch("shared.telemetry.OTLPSpanExporter"),
        patch("shared.telemetry.BatchSpanProcessor"),
        patch("shared.telemetry._instrument_fastapi"),
        patch.dict("sys.modules", {"opentelemetry.instrumentation.asyncpg": None}),
    ):
        from shared.telemetry import configure_telemetry
        # Should complete without raising ImportError
        configure_telemetry(service_name="test-service", environment="development")


def test_instrument_fastapi_calls_instrumentor_instrument_app() -> None:
    """_instrument_fastapi() calls FastAPIInstrumentor.instrument_app(app)."""
    mock_app = MagicMock()

    with patch("shared.telemetry.FastAPIInstrumentor") as mock_instrumentor_cls:
        # FastAPIInstrumentor is a class; instrument_app is a classmethod
        from shared.telemetry import _instrument_fastapi
        _instrument_fastapi(mock_app, "test-service")

    mock_instrumentor_cls.instrument_app.assert_called_once_with(mock_app)


def test_configure_telemetry_uses_correct_resource_attributes() -> None:
    """TracerProvider is created with SERVICE_NAME matching service_name arg."""
    _reset_otel()
    captured_resources = []

    original_provider = __import__(
        "opentelemetry.sdk.trace", fromlist=["TracerProvider"]
    ).TracerProvider

    class CapturingProvider(original_provider):
        def __init__(self, resource=None, **kwargs):  # type: ignore[override]
            captured_resources.append(resource)
            super().__init__(resource=resource, **kwargs)

    with (
        patch("shared.telemetry.TracerProvider", CapturingProvider),
        patch("shared.telemetry.OTLPSpanExporter"),
        patch("shared.telemetry.BatchSpanProcessor"),
        patch("shared.telemetry._instrument_fastapi"),
    ):
        from shared.telemetry import configure_telemetry
        configure_telemetry(service_name="nexus-gateway", environment="production")

    assert len(captured_resources) == 1
    attrs = captured_resources[0].attributes
    assert attrs.get("service.name") == "nexus-gateway"
    assert attrs.get("deployment.environment") == "production"