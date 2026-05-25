"""
Shared pytest fixtures for NEXUS unit tests.

Unit tests run in CI without Docker — all external dependencies (DB, Redis,
Kafka) must be mocked. Import shared fixtures from this file in test modules.
"""

import pytest


@pytest.fixture()
def mock_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Override settings for unit tests to avoid pydantic-settings validation errors."""
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://nexus:nexus@localhost:5432/nexus")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("JWT_SECRET_KEY", "ci-test-secret-key-exactly-32-chars")
    monkeypatch.setenv("JWT_ALGORITHM", "HS256")
    monkeypatch.setenv("ORCHESTRATOR_URL", "http://localhost:8001")
    monkeypatch.setenv("ENVIRONMENT", "test")