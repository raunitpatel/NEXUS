# services/shared/kafka_client.py
"""
Shared Kafka producer/consumer utilities for NEXUS services.

All services that produce or consume Kafka messages import from this module.
The module provides:

  KafkaProducerFactory  — singleton async producer, bytes-passthrough serializer
  KafkaConsumerFactory  — per-call consumer creation with async context manager
  publish_message()     — convenience wrapper for fire-and-wait publish
  close_producer()      — called from service lifespan shutdown

Design decisions:
  - Producer uses a raw bytes serializer (value_serializer=lambda v: v if isinstance(v, bytes) else v.encode()).
    All NEXUS producers pass pre-serialised bytes via Pydantic .model_dump_json().encode()
    so the factory must NOT apply a second json.dumps layer.
  - The singleton pattern prevents TCP connection churn — one producer per process.
  - Consumer is NOT a singleton because each consumer group/topic pair requires
    independent offset tracking.

Usage (producer):
    from shared.kafka_client import KafkaProducerFactory, publish_message
    from shared.kafka_schemas import EventMessage

    producer = await KafkaProducerFactory.get_producer(settings.kafka_bootstrap_servers)
    event = EventMessage(run_id=..., event_type="thought", source="orchestrator", payload={})
    await publish_message(producer, settings.kafka_topic_events, event.model_dump_json().encode())

Usage (consumer):
    from shared.kafka_client import KafkaConsumerFactory

    async with KafkaConsumerFactory.create_consumer(
        topic=settings.kafka_topic_tasks,
        bootstrap_servers=settings.kafka_bootstrap_servers,
        group_id=settings.kafka_consumer_group_orchestrator,
    ) as consumer:
        async for msg in consumer:
            payload = TaskDispatchedMessage.model_validate_json(msg.value)
            ...
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from aiokafka.errors import KafkaConnectionError, KafkaTimeoutError

logger = logging.getLogger(__name__)


# Serializers


def _bytes_serializer(value: bytes | str | dict[str, Any]) -> bytes:
    """
    Passthrough serializer for the Kafka producer.

    NEXUS nodes always pass pre-serialised bytes (Pydantic .model_dump_json().encode()).
    If a raw dict or str is passed (e.g. from tests), it is JSON-encoded as a fallback.

    Args:
        value: The message value to serialise.

    Returns:
        Raw bytes ready to write to Kafka.
    """
    if isinstance(value, bytes):
        return value
    if isinstance(value, str):
        return value.encode("utf-8")
    # dict fallback — should not happen in production paths
    return json.dumps(value).encode("utf-8")


def _bytes_deserializer(value: bytes) -> bytes:
    """
    Passthrough deserializer for the Kafka consumer.

    Consumers are responsible for calling the correct Pydantic
    .model_validate_json() on the raw bytes — the factory does not
    deserialise to dict because different topics use different schemas.

    Args:
        value: Raw bytes from Kafka.

    Returns:
        The same bytes, unchanged.
    """
    return value


# Producer factory


class KafkaProducerFactory:
    """
    Singleton async Kafka producer for a given bootstrap_servers string.

    One producer instance is created per process on first call to get_producer().
    Subsequent calls return the same started instance. The producer is closed
    via close() during service lifespan shutdown.

    Thread/task safety: AIOKafkaProducer is not thread-safe but is coroutine-safe
    within a single asyncio event loop, which is the NEXUS model.
    """

    _producer: AIOKafkaProducer | None = None
    _bootstrap_servers: str | None = None
    _lock: asyncio.Lock = asyncio.Lock()

    @classmethod
    async def get_producer(
        cls,
        bootstrap_servers: str,
        *,
        request_timeout_ms: int = 10_000,
        retry_backoff_ms: int = 500,
        max_batch_size: int = 65_536,
        compression_type: str | None = None,
    ) -> AIOKafkaProducer:
        """
        Return a started singleton AIOKafkaProducer.

        Creates and starts the producer on first call. Subsequent calls with
        the same bootstrap_servers return the cached instance immediately.
        If bootstrap_servers changes (e.g. in tests), the old producer is closed
        and a new one is created.

        Args:
            bootstrap_servers: Comma-separated Kafka broker addresses.
                            Matches KAFKA_BOOTSTRAP_SERVERS env var.
            request_timeout_ms: Milliseconds before a produce request times out.
            retry_backoff_ms: Milliseconds between retry attempts on transient errors.
            max_batch_size: Maximum bytes per batch before flushing.
            compression_type: Optional compression — None, "gzip", "snappy", "lz4".

        Returns:
            A started AIOKafkaProducer ready to call .send() on.

        Raises:
            KafkaConnectionError: If the broker is unreachable after retries.
        """
        async with cls._lock:
            if cls._producer is not None and cls._bootstrap_servers == bootstrap_servers:
                return cls._producer

            # bootstrap_servers changed (test isolation) — close old producer
            if cls._producer is not None:
                try:
                    await cls._producer.stop()
                except Exception:
                    pass
                cls._producer = None

            producer = AIOKafkaProducer(
                bootstrap_servers=bootstrap_servers,
                value_serializer=_bytes_serializer,
                request_timeout_ms=request_timeout_ms,
                retry_backoff_ms=retry_backoff_ms,
                max_batch_size=max_batch_size,
                compression_type=compression_type,
                # Enable idempotent producer for exactly-once delivery per session
                enable_idempotence=False,  # set True when brokers support it
            )

            try:
                await producer.start()
                logger.info(
                    "kafka_producer.started",
                    extra={"bootstrap_servers": bootstrap_servers},
                )
            except KafkaConnectionError as exc:
                logger.error(
                    "kafka_producer.connection_failed",
                    extra={"bootstrap_servers": bootstrap_servers, "error": str(exc)},
                )
                raise

            cls._producer = producer
            cls._bootstrap_servers = bootstrap_servers
            return cls._producer

    @classmethod
    async def close(cls) -> None:
        """
        Gracefully stop the singleton producer.

        Called from each service's lifespan shutdown block. Safe to call
        if the producer was never started (no-op).
        """
        async with cls._lock:
            if cls._producer is not None:
                try:
                    await cls._producer.stop()
                    logger.info("kafka_producer.stopped")
                except Exception as exc:
                    logger.warning("kafka_producer.stop_error", extra={"error": str(exc)})
                finally:
                    cls._producer = None
                    cls._bootstrap_servers = None

    @classmethod
    async def ping(cls, bootstrap_servers: str) -> bool:
        """
        Check whether the Kafka broker is reachable by starting a temporary producer.

        Used in service lifespan health checks. Does not affect the singleton.

        Args:
            bootstrap_servers: Broker address string.

        Returns:
            True if broker responded within 5 seconds, False otherwise.
        """
        probe = AIOKafkaProducer(
            bootstrap_servers=bootstrap_servers,
            request_timeout_ms=5_000,
        )
        try:
            await asyncio.wait_for(probe.start(), timeout=5.0)
            await probe.stop()
            return True
        except Exception:
            return False


# Consumer factory


class KafkaConsumerFactory:
    """
    Factory for creating per-call AIOKafkaConsumer instances.

    Consumers are not singletons — each topic/group pair gets its own consumer
    with independent offset tracking. Consumers should be created inside async
    context managers to ensure clean stop() on exit.
    """

    @staticmethod
    @asynccontextmanager
    async def create_consumer(
        topic: str,
        bootstrap_servers: str,
        group_id: str,
        *,
        auto_offset_reset: str = "earliest",
        session_timeout_ms: int = 30_000,
        heartbeat_interval_ms: int = 3_000,
        max_poll_records: int = 10,
        enable_auto_commit: bool = True,
    ) -> AsyncIterator[AIOKafkaConsumer]:
        """
        Async context manager that yields a started AIOKafkaConsumer.

        Ensures consumer.stop() is always called on exit, even on exception.

        Args:
            topic: Kafka topic name to subscribe to (e.g. "nexus.tasks").
            bootstrap_servers: Comma-separated broker addresses.
            group_id: Consumer group ID for offset coordination.
            auto_offset_reset: "earliest" or "latest" — where to start if no committed offset.
            session_timeout_ms: Milliseconds before broker considers consumer dead.
            heartbeat_interval_ms: How often the consumer sends heartbeats.
            max_poll_records: Maximum records returned per poll call.
            enable_auto_commit: Whether to auto-commit offsets. Set False for
                                manual commit in exactly-once processing.

        Yields:
            A started AIOKafkaConsumer subscribed to the given topic.

        Raises:
            KafkaConnectionError: If broker is unreachable during start.

        Example:
            async with KafkaConsumerFactory.create_consumer(
                topic="nexus.tasks",
                bootstrap_servers="kafka:9092",
                group_id="nexus-orchestrator",
            ) as consumer:
                async for msg in consumer:
                    data = TaskDispatchedMessage.model_validate_json(msg.value)
        """
        consumer = AIOKafkaConsumer(
            topic,
            bootstrap_servers=bootstrap_servers,
            group_id=group_id,
            auto_offset_reset=auto_offset_reset,
            value_deserializer=_bytes_deserializer,
            session_timeout_ms=session_timeout_ms,
            heartbeat_interval_ms=heartbeat_interval_ms,
            max_poll_records=max_poll_records,
            enable_auto_commit=enable_auto_commit,
        )

        try:
            await consumer.start()
            logger.info(
                "kafka_consumer.started",
                extra={"topic": topic, "group_id": group_id},
            )
            yield consumer
        finally:
            try:
                await consumer.stop()
                logger.info(
                    "kafka_consumer.stopped",
                    extra={"topic": topic, "group_id": group_id},
                )
            except Exception as exc:
                logger.warning(
                    "kafka_consumer.stop_error",
                    extra={"topic": topic, "error": str(exc)},
                )


# Convenience publish helper


async def publish_message(
    producer: AIOKafkaProducer,
    topic: str,
    payload: bytes | str | dict[str, Any],
    *,
    key: bytes | None = None,
    partition: int | None = None,
) -> None:
    """
    Send a single message to a Kafka topic and wait for broker acknowledgement.

    Wraps producer.send_and_wait() with structured error logging. Does not raise
    on KafkaTimeoutError — logs warning and returns so callers (node event publishers)
    don't abort runs on non-critical Kafka failures.

    Args:
        producer: A started AIOKafkaProducer from KafkaProducerFactory.get_producer().
        topic: Target Kafka topic name.
        payload: Message value — bytes, str, or dict. Serialised by _bytes_serializer.
        key: Optional message key bytes for partition routing.
        partition: Optional explicit partition override.

    Raises:
        KafkaConnectionError: On broker connection loss (caller should handle).
    """
    try:
        await producer.send_and_wait(
            topic,
            value=payload,
            key=key,
            partition=partition,
        )
        logger.debug("kafka.publish_message.sent", extra={"topic": topic})
    except KafkaTimeoutError as exc:
        logger.warning(
            "kafka.publish_message.timeout",
            extra={"topic": topic, "error": str(exc)},
        )
    except Exception as exc:
        logger.error(
            "kafka.publish_message.error",
            extra={"topic": topic, "error": str(exc)},
        )
        raise
