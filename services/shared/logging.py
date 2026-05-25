"""
Structured JSON logging configuration for all NEXUS services.

Every service calls configure_logging() once at startup (inside the lifespan
context manager) before any log statements are emitted. After that call,
all structlog loggers in that process emit newline-delimited JSON — one object
per log event — ready for ingestion by Datadog, Grafana Loki, or Railway's
log drain.

Usage (in each service's main.py lifespan):
    from shared.logging import configure_logging
    configure_logging(level=settings.log_level)

Then anywhere in the service:
    import structlog
    logger = structlog.get_logger(__name__)
    logger.info("event.name", key="value")
"""

import logging
import sys
from typing import Any

import structlog


def configure_logging(level: str = "INFO") -> None:
    """
    Configure structlog for JSON output across the entire service process.

    Sets up a shared processor chain used by both structlog loggers and the
    standard-library logging bridge so that third-party libraries (SQLAlchemy,
    uvicorn, httpx) also emit structured JSON.

    Args:
        level: Python logging level string — "DEBUG", "INFO", "WARNING", "ERROR".
               Loaded from settings.log_level in each service; defaults to "INFO".
    """

    log_level: int = getattr(logging, level.upper(), logging.INFO)

    # Shared processor applied to every log record regardless of origin
    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    # Configure the standard-library root logger to route through structlog
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=log_level,
    )

    # Silence noisy third-party loggers that would otherwise flood output
    for noisy in ("uvicorn.access", "sqlalchemy.engine", "httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    structlog.configure(
        processors=shared_processors
        + [
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Attach a structlog ProcessorFormatter to the root logger so stdlib
    # log records (from uvicorn, SQLAlchemy, etc.) also emit JSON
    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.JSONRenderer(),
        ],
        foreign_pre_chain=shared_processors,
    )

    root_logger = logging.getLogger()
    for handler in root_logger.handlers:
        handler.setFormatter(formatter)
