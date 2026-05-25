"""
Unit tests for services/memory_agent/agent.py, embeddings.py, and pgvector_store.py.

All external dependencies (asyncpg, Redis, SentenceTransformer, Kafka) are mocked.
No Docker containers required.

Run:
    docker exec nexus-memory-agent python -m pytest tests/ -v --asyncio-mode=auto
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── Fixtures ──────────────────────────────────────────────────────────────────


def _mock_pool() -> AsyncMock:
    """Return a mock asyncpg pool."""
    pool = AsyncMock()
    return pool


def _mock_redis() -> AsyncMock:
    """Return a mock async Redis client."""
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    redis.set = AsyncMock(return_value=True)
    return redis


def _fake_embedding(dim: int = 384) -> list[float]:
    """Return a fake normalized embedding vector."""
    val = 1.0 / (dim**0.5)
    return [val] * dim


def _fake_search_results() -> list[dict[str, Any]]:
    return [
        {
            "id": "emb-001",
            "run_id": "run-001",
            "task_id": "task-001",
            "content": "LangGraph uses stateful graphs for orchestration",
            "similarity": 0.92,
            "model": "all-MiniLM-L6-v2",
            "metadata": {},
            "created_at": "2025-01-01T00:00:00+00:00",
        },
        {
            "id": "emb-002",
            "run_id": "run-001",
            "task_id": None,
            "content": "Orchestration with async agents",
            "similarity": 0.81,
            "model": "all-MiniLM-L6-v2",
            "metadata": {},
            "created_at": "2025-01-01T00:00:01+00:00",
        },
    ]


# ── EmbeddingModel tests ──────────────────────────────────────────────────────


def test_embedding_model_encode_returns_384_floats() -> None:
    """EmbeddingModel.encode() returns list of 384 floats."""
    mock_st = MagicMock()
    import numpy as np

    mock_st.encode.return_value = np.array(_fake_embedding(384))

    with patch("embeddings.SentenceTransformer", return_value=mock_st):
        from embeddings import EmbeddingModel

        # Reset singleton for test isolation
        EmbeddingModel._instance = None
        model = EmbeddingModel()
        result = model.encode("test text")

    assert len(result) == 384
    assert all(isinstance(v, float) for v in result)


def test_embedding_model_singleton_returns_same_instance() -> None:
    """EmbeddingModel() always returns the same singleton instance."""
    mock_st = MagicMock()
    import numpy as np

    mock_st.encode.return_value = np.array(_fake_embedding())

    with patch("embeddings.SentenceTransformer", return_value=mock_st):
        from embeddings import EmbeddingModel

        EmbeddingModel._instance = None
        m1 = EmbeddingModel()
        m2 = EmbeddingModel()

    assert m1 is m2


# ── MemoryAgent.embed() tests ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_embed_calls_insert_embedding_and_returns_result() -> None:
    """embed() calls insert_embedding with correct args and returns EmbedResult."""
    from agent import MemoryAgent

    pool = _mock_pool()
    redis = _mock_redis()

    with (
        patch("agent.EmbeddingModel") as mock_model_cls,
        patch("agent.insert_embedding", new_callable=AsyncMock, return_value="emb-uuid-001"),
    ):
        mock_model = MagicMock()
        mock_model.encode.return_value = _fake_embedding()
        mock_model.dimensions = 384
        mock_model_cls.return_value = mock_model

        agent = MemoryAgent(db_pool=pool, redis_client=redis)
        result = await agent.embed(
            run_id="run-001",
            content="LangGraph uses stateful graphs",
            content_type="task_output",
            task_id="task-001",
            user_id="user-001",
        )

    assert result.embedding_id == "emb-uuid-001"
    assert result.dimensions == 384
    assert result.duration_ms >= 0


@pytest.mark.asyncio
async def test_embed_result_to_dict_has_required_fields() -> None:
    """EmbedResult.to_dict() has embedding_id, dimensions, duration_ms."""
    from agent import MemoryAgent

    with (
        patch("agent.EmbeddingModel") as mock_model_cls,
        patch("agent.insert_embedding", new_callable=AsyncMock, return_value="emb-001"),
    ):
        mock_model = MagicMock()
        mock_model.encode.return_value = _fake_embedding()
        mock_model.dimensions = 384
        mock_model_cls.return_value = mock_model

        agent = MemoryAgent(db_pool=_mock_pool(), redis_client=_mock_redis())
        result = await agent.embed(run_id="r1", content="test")

    d = result.to_dict()
    assert "embedding_id" in d
    assert "dimensions" in d
    assert "duration_ms" in d


# ── MemoryAgent.search() tests ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_search_cache_miss_calls_pgvector_and_writes_redis() -> None:
    """On cache miss, search() calls cosine_search and writes result to Redis."""
    from agent import MemoryAgent

    redis = _mock_redis()
    redis.get = AsyncMock(return_value=None)  # cache miss

    with (
        patch("agent.EmbeddingModel") as mock_model_cls,
        patch("agent.cosine_search", new_callable=AsyncMock, return_value=_fake_search_results()),
    ):
        mock_model = MagicMock()
        mock_model.encode.return_value = _fake_embedding()
        mock_model.dimensions = 384
        mock_model_cls.return_value = mock_model

        agent = MemoryAgent(db_pool=_mock_pool(), redis_client=redis)
        result = await agent.search(user_id="user-001", query_text="orchestration")

    assert result.from_cache is False
    assert len(result.results) == 2
    assert result.results[0]["similarity"] > result.results[1]["similarity"]
    redis.set.assert_awaited_once()
    set_kwargs = redis.set.call_args[1]
    assert set_kwargs["ex"] == 300


@pytest.mark.asyncio
async def test_search_cache_hit_skips_pgvector() -> None:
    """On cache hit, search() returns cached data without calling cosine_search."""
    from agent import MemoryAgent

    cached = json.dumps(_fake_search_results())
    redis = _mock_redis()
    redis.get = AsyncMock(return_value=cached)

    with (
        patch("agent.EmbeddingModel") as mock_model_cls,
        patch("agent.cosine_search", new_callable=AsyncMock) as mock_search,
    ):
        mock_model = MagicMock()
        mock_model.encode.return_value = _fake_embedding()
        mock_model.dimensions = 384
        mock_model_cls.return_value = mock_model

        agent = MemoryAgent(db_pool=_mock_pool(), redis_client=redis)
        result = await agent.search(user_id="user-001", query_text="orchestration")

    assert result.from_cache is True
    assert len(result.results) == 2
    mock_search.assert_not_awaited()


@pytest.mark.asyncio
async def test_search_redis_failure_falls_through_to_pgvector() -> None:
    """Redis read error causes cache miss — cosine_search is still called."""
    from agent import MemoryAgent

    redis = _mock_redis()
    redis.get = AsyncMock(side_effect=Exception("Redis connection refused"))

    with (
        patch("agent.EmbeddingModel") as mock_model_cls,
        patch("agent.cosine_search", new_callable=AsyncMock, return_value=_fake_search_results()),
    ):
        mock_model = MagicMock()
        mock_model.encode.return_value = _fake_embedding()
        mock_model.dimensions = 384
        mock_model_cls.return_value = mock_model

        agent = MemoryAgent(db_pool=_mock_pool(), redis_client=redis)
        result = await agent.search(user_id="user-001", query_text="test query")

    assert result.from_cache is False
    assert len(result.results) == 2


@pytest.mark.asyncio
async def test_search_results_ordered_by_similarity_descending() -> None:
    """Search results are always returned with highest similarity first."""
    from agent import MemoryAgent

    unordered = [
        {**_fake_search_results()[1], "similarity": 0.75},
        {**_fake_search_results()[0], "similarity": 0.95},
    ]

    redis = _mock_redis()
    redis.get = AsyncMock(return_value=None)

    with (
        patch("agent.EmbeddingModel") as mock_model_cls,
        patch("agent.cosine_search", new_callable=AsyncMock, return_value=unordered),
    ):
        mock_model = MagicMock()
        mock_model.encode.return_value = _fake_embedding()
        mock_model.dimensions = 384
        mock_model_cls.return_value = mock_model

        agent = MemoryAgent(db_pool=_mock_pool(), redis_client=redis)
        result = await agent.search(user_id="user-001", query_text="test")

    scores = [r["similarity"] for r in result.results]
    assert scores == sorted(scores, reverse=True)


@pytest.mark.asyncio
async def test_cache_key_format_includes_user_id_and_hash() -> None:
    """Cache key matches pattern vsearch:{user_id}:{sha256_hex}."""
    from agent import MemoryAgent

    with patch("agent.EmbeddingModel") as mock_model_cls:
        mock_model_cls.return_value = MagicMock(dimensions=384)
        agent = MemoryAgent(db_pool=_mock_pool(), redis_client=_mock_redis())

    key = agent._make_cache_key("user-abc", "some query text")
    assert key.startswith("vsearch:user-abc:")
    assert len(key) > len("vsearch:user-abc:") + 10  # SHA-256 is 64 hex chars


# ── main.py endpoint tests ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_healthz_returns_ok() -> None:
    """GET /healthz returns 200 with status ok."""
    from fastapi.testclient import TestClient
    from main import app

    with TestClient(app) as client:
        response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_run_endpoint_missing_content_for_write_returns_error() -> None:
    """POST /run with empty input.content for memory_write returns error."""
    from fastapi.testclient import TestClient
    from main import app

    with TestClient(app) as client:
        response = client.post(
            "/run",
            json={
                "run_id": "r1",
                "task_id": "t1",
                "user_id": "u1",
                "task_type": "memory_write",
                "input": {},
                "attempt": 1,
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert data["error"] == "input.content is required for memory_write"


@pytest.mark.asyncio
async def test_run_endpoint_missing_query_for_read_returns_error() -> None:
    """POST /run with empty input.query for memory_read returns error."""
    from fastapi.testclient import TestClient
    from main import app

    with TestClient(app) as client:
        response = client.post(
            "/run",
            json={
                "run_id": "r1",
                "task_id": "t1",
                "user_id": "u1",
                "task_type": "memory_read",
                "input": {},
                "attempt": 1,
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert data["error"] == "input.query is required for memory_read"


@pytest.mark.asyncio
async def test_run_endpoint_unknown_task_type_returns_error() -> None:
    """POST /run with unknown task_type returns descriptive error."""
    from fastapi.testclient import TestClient
    from main import app

    with TestClient(app) as client:
        response = client.post(
            "/run",
            json={
                "run_id": "r1",
                "task_id": "t1",
                "user_id": "u1",
                "task_type": "summarize",
                "input": {"content": "test"},
                "attempt": 1,
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert "Unknown task_type" in data["error"]
