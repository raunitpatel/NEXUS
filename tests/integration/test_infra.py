# nexus/tests/integration/test_infra.py
"""
Integration tests for NEXUS infrastructure containers (AGNT-001).

Precondition: Run scripts/start-infra.ps1 before executing these tests.
These tests verify that all stateful containers are reachable and healthy.

Run:
    cd nexus
    python -m pytest tests/integration/test_infra.py -v
"""
from __future__ import annotations

import asyncio
import socket
from typing import Generator
from dotenv import load_dotenv  
import os

import pytest
import pytest_asyncio

load_dotenv(dotenv_path=".env")


def _tcp_reachable(host: str, port: int, timeout: float = 5.0) -> bool:
    """Check if a TCP port is open and accepting connections."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (socket.error, ConnectionRefusedError, TimeoutError):
        return False


class TestPostgresReachability:
    """Verify PostgreSQL container is reachable and pgvector is enabled."""

    def test_postgres_tcp_reachable(self) -> None:
        """PostgreSQL must accept TCP connections on localhost:5434."""
        assert _tcp_reachable("localhost", 5434), (
            "PostgreSQL is not reachable on localhost:5434. "
            "Run: .\\scripts\\start-infra.ps1"
        )

    def test_postgres_pgvector_extension(self) -> None:
        """pgvector extension must be installed in nexus_db."""
        import psycopg2  # type: ignore[import]

        conn = psycopg2.connect(
            host="localhost",
            port=os.getenv("POSTGRES_PORT", 5432),
            user=os.getenv("POSTGRES_USER", "nexus"),
            password=os.getenv("POSTGRES_PASSWORD"),
            dbname=os.getenv("POSTGRES_DB", "nexus_db"),
            connect_timeout=15,
        )
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT extname FROM pg_extension WHERE extname = 'vector';"
                )
                row = cur.fetchone()
                assert row is not None, "pgvector extension not found in nexus_db"
                assert row[0] == "vector"
        finally:
            conn.close()


class TestRedisReachability:
    """Verify Redis container is reachable and responds to PING."""

    def test_redis_tcp_reachable(self) -> None:
        """Redis must accept TCP connections on localhost:6379."""
        assert _tcp_reachable("localhost", 6379), (
            "Redis is not reachable on localhost:6379. "
            "Run: .\\scripts\\start-infra.ps1"
        )

    def test_redis_ping(self) -> None:
        """Redis must respond PONG to PING with the configured password."""
        import redis  # type: ignore[import]

        client = redis.Redis(
            host="localhost",
            port=6379,
            password=os.getenv("REDIS_PASSWORD", "nexus_secret"),
            socket_connect_timeout=5,
            socket_timeout=5,
        )
        try:
            response = client.ping()
            assert response is True, "Redis PING did not return True"
        finally:
            client.close()


class TestKafkaReachability:
    """Verify Kafka broker is reachable."""

    def test_kafka_tcp_reachable(self) -> None:
        """Kafka must accept TCP connections on localhost:29092 (external listener)."""
        assert _tcp_reachable("localhost", 29092), (
            "Kafka is not reachable on localhost:29092. "
            "Run: .\\scripts\\start-infra.ps1"
        )

    def test_kafka_topics_exist(self) -> None:
        """All three NEXUS Kafka topics must exist after start-infra.ps1 runs."""
        from kafka import KafkaAdminClient  # type: ignore[import]
        from kafka.errors import NoBrokersAvailable  # type: ignore[import]

        try:
            admin = KafkaAdminClient(
                bootstrap_servers="localhost:29092",
                client_id="nexus-test-client",
                request_timeout_ms=5000,
            )
            topics = admin.list_topics()
            admin.close()
        except NoBrokersAvailable as exc:
            pytest.fail(f"Kafka broker not available: {exc}")

        required_topics = {"nexus.tasks", "nexus.results", "nexus.events"}
        missing = required_topics - set(topics)
        assert not missing, (
            f"Missing Kafka topics: {missing}. "
            "Run: .\\scripts\\start-infra.ps1 to create topics."
        )


class TestZookeeperReachability:
    """Verify Zookeeper is reachable."""

    def test_zookeeper_tcp_reachable(self) -> None:
        """Zookeeper must accept TCP connections on localhost:2181."""
        assert _tcp_reachable("localhost", 2181), (
            "Zookeeper is not reachable on localhost:2181. "
            "Run: .\\scripts\\start-infra.ps1"
        )