"""
Shared Kafka producer/consumer utilities for NEXUS services.
"""

from __future__ import annotations

import json
from typing import Any

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer


class KafkaProducerFactory:
    """
    Singleton-style Kafka producer factory.

    Ensures all services reuse a single producer instance instead of
    creating new TCP connections repeatedly.
    """

    _producer: AIOKafkaProducer | None = None

    @classmethod
    async def get_producer(
        cls,
        bootstrap_servers: str,
    ) -> AIOKafkaProducer:
        """
        Return a started Kafka producer instance.

        Creates and starts producer lazily on first call.
        """

        if cls._producer is None:
            cls._producer = AIOKafkaProducer(
                bootstrap_servers=bootstrap_servers,
                value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            )

            await cls._producer.start()

        return cls._producer

    @classmethod
    async def close(cls) -> None:
        """
        Gracefully stop producer during application shutdown.
        """

        if cls._producer is not None:
            await cls._producer.stop()
            cls._producer = None


class KafkaConsumerFactory:
    """
    Convenience factory for creating Kafka consumers.
    """

    @staticmethod
    async def create_consumer(
        topic: str,
        bootstrap_servers: str,
        group_id: str,
        auto_offset_reset: str = "earliest",
    ) -> AIOKafkaConsumer:
        """
        Create and start a Kafka consumer.
        """

        consumer = AIOKafkaConsumer(
            topic,
            bootstrap_servers=bootstrap_servers,
            group_id=group_id,
            auto_offset_reset=auto_offset_reset,
            value_deserializer=lambda v: json.loads(v.decode("utf-8")),
        )

        await consumer.start()

        return consumer


async def publish_message(
    producer: AIOKafkaProducer,
    topic: str,
    payload: dict[str, Any],
) -> None:
    """
    Publish JSON message to Kafka topic.
    """

    await producer.send_and_wait(
        topic,
        payload,
    )