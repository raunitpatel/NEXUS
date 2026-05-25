"""
Unit tests for services/gateway/routers/sse.py.

All external dependencies (DB, Redis, httpx, Orchestrator) are mocked.
Tests run in isolation — no Docker containers required.

Run:
    docker exec nexus-gateway python -m pytest tests/ -v --asyncio-mode=auto
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import status
from jose import jwt
from starlette.testclient import TestClient

TEST_SECRET = "test-secret-key-exactly-32-chars!!"
TEST_ALGORITHM = "HS256"


def _make_token(user_id: str, jti: str | None = None, expired: bool = False) -> str:
    jti = jti or str(uuid.uuid4())
    now = datetime.now(tz=UTC)
    delta = timedelta(seconds=-1) if expired else timedelta(hours=24)
    payload = {"sub": user_id, "jti": jti, "iat": now, "exp": now + delta}
    return jwt.encode(payload, TEST_SECRET, algorithm=TEST_ALGORITHM)


def _patch_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JWT_SECRET_KEY", TEST_SECRET)
    monkeypatch.setenv("JWT_ALGORITHM", TEST_ALGORITHM)
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://x:x@localhost/x")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("ORCHESTRATOR_URL", "http://orchestrator:8001")


# ── _validate_token tests ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_validate_token_valid_returns_user_id(monkeypatch: pytest.MonkeyPatch) -> None:
    """Valid JWT + live Redis session returns user_id string."""
    _patch_settings(monkeypatch)
    import config as cfg

    cfg.settings.jwt_secret_key = TEST_SECRET
    cfg.settings.jwt_algorithm = TEST_ALGORITHM

    from routers.sse import _validate_token

    user_id = str(uuid.uuid4())
    token = _make_token(user_id)

    mock_redis = AsyncMock()
    mock_redis.exists = AsyncMock(return_value=1)

    result = await _validate_token(token, mock_redis)
    assert result == user_id


@pytest.mark.asyncio
async def test_validate_token_expired_raises_401(monkeypatch: pytest.MonkeyPatch) -> None:
    """Expired JWT raises 401 HTTPException."""
    _patch_settings(monkeypatch)
    import config as cfg

    cfg.settings.jwt_secret_key = TEST_SECRET
    cfg.settings.jwt_algorithm = TEST_ALGORITHM

    from fastapi import HTTPException
    from routers.sse import _validate_token

    token = _make_token(str(uuid.uuid4()), expired=True)
    mock_redis = AsyncMock()

    with pytest.raises(HTTPException) as exc_info:
        await _validate_token(token, mock_redis)

    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.asyncio
async def test_validate_token_no_session_raises_401(monkeypatch: pytest.MonkeyPatch) -> None:
    """Valid JWT but missing Redis session raises 401."""
    _patch_settings(monkeypatch)
    import config as cfg

    cfg.settings.jwt_secret_key = TEST_SECRET
    cfg.settings.jwt_algorithm = TEST_ALGORITHM

    from fastapi import HTTPException
    from routers.sse import _validate_token

    token = _make_token(str(uuid.uuid4()))
    mock_redis = AsyncMock()
    mock_redis.exists = AsyncMock(return_value=0)  # session not found

    with pytest.raises(HTTPException) as exc_info:
        await _validate_token(token, mock_redis)

    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.asyncio
async def test_validate_token_redis_error_raises_503(monkeypatch: pytest.MonkeyPatch) -> None:
    """Redis error during session check raises 503."""
    _patch_settings(monkeypatch)
    import config as cfg

    cfg.settings.jwt_secret_key = TEST_SECRET
    cfg.settings.jwt_algorithm = TEST_ALGORITHM

    from fastapi import HTTPException
    from routers.sse import _validate_token

    token = _make_token(str(uuid.uuid4()))
    mock_redis = AsyncMock()
    mock_redis.exists = AsyncMock(side_effect=Exception("Redis down"))

    with pytest.raises(HTTPException) as exc_info:
        await _validate_token(token, mock_redis)

    assert exc_info.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE


# ── _verify_run_ownership tests ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_verify_ownership_matching_user_passes() -> None:
    """Run owned by the requesting user does not raise."""
    from routers.sse import _verify_run_ownership

    user_id = str(uuid.uuid4())
    run_id = str(uuid.uuid4())

    mock_row = MagicMock()
    mock_row.user_id = user_id

    mock_result = MagicMock()
    mock_result.fetchone.return_value = mock_row

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    mock_request = MagicMock()
    mock_engine = MagicMock()
    mock_request.app.state.db_engine = mock_engine

    with patch("routers.sse.async_sessionmaker", return_value=MagicMock(return_value=mock_session)):
        # Should not raise
        await _verify_run_ownership(run_id, user_id, mock_request)


@pytest.mark.asyncio
async def test_verify_ownership_wrong_user_raises_403() -> None:
    """Run owned by different user raises 403."""
    from fastapi import HTTPException
    from routers.sse import _verify_run_ownership

    requesting_user = str(uuid.uuid4())
    run_owner = str(uuid.uuid4())
    run_id = str(uuid.uuid4())

    mock_row = MagicMock()
    mock_row.user_id = run_owner  # different user owns the run

    mock_result = MagicMock()
    mock_result.fetchone.return_value = mock_row

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    mock_request = MagicMock()
    mock_request.app.state.db_engine = MagicMock()

    with patch("routers.sse.async_sessionmaker", return_value=MagicMock(return_value=mock_session)):
        with pytest.raises(HTTPException) as exc_info:
            await _verify_run_ownership(run_id, requesting_user, mock_request)

    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
async def test_verify_ownership_run_not_found_raises_404() -> None:
    """Non-existent run_id raises 404."""
    from fastapi import HTTPException
    from routers.sse import _verify_run_ownership

    mock_result = MagicMock()
    mock_result.fetchone.return_value = None  # run not found

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    mock_request = MagicMock()
    mock_request.app.state.db_engine = MagicMock()

    with patch("routers.sse.async_sessionmaker", return_value=MagicMock(return_value=mock_session)):
        with pytest.raises(HTTPException) as exc_info:
            await _verify_run_ownership("nonexistent-id", str(uuid.uuid4()), mock_request)

    assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND


# ── _proxy_stream tests ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_proxy_stream_forwards_chunks() -> None:
    """_proxy_stream yields bytes from Orchestrator response."""
    from routers.sse import _proxy_stream

    chunk1 = b'data: {"event_type":"thought","payload":{"content":"planning"}}\n\n'
    chunk2 = b'data: {"event_type":"run_complete","payload":{}}\n\n'

    async def mock_aiter_bytes():
        yield chunk1
        yield chunk2

    mock_response = AsyncMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.aiter_bytes = mock_aiter_bytes
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=False)

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.stream = MagicMock(return_value=mock_response)

    with patch("routers.sse.httpx.AsyncClient", return_value=mock_client):
        collected = []
        async for chunk in _proxy_stream("run-test-001"):
            collected.append(chunk)

    assert chunk1 in collected
    assert chunk2 in collected
    # Stream stops after run_complete — exactly 2 chunks
    assert len(collected) == 2


@pytest.mark.asyncio
async def test_proxy_stream_orchestrator_down_yields_error_event() -> None:
    """_proxy_stream yields error SSE event when Orchestrator is unreachable."""
    import httpx
    from routers.sse import _proxy_stream

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.stream = MagicMock(side_effect=httpx.ConnectError("refused"))

    with patch("routers.sse.httpx.AsyncClient", return_value=mock_client):
        collected = []
        async for chunk in _proxy_stream("run-test-002"):
            collected.append(chunk)

    assert len(collected) == 1
    assert b"error" in collected[0]
    assert b"unavailable" in collected[0].lower()


# ── stream_run endpoint smoke tests ───────────────────────────────────────────


def test_stream_run_missing_token_returns_422() -> None:
    """GET /api/v1/sse/{run_id} without ?token= returns 422 (required query param)."""
    # Import after env patches to avoid settings validation errors
    import importlib

    import config as cfg

    cfg.settings.jwt_secret_key = TEST_SECRET
    cfg.settings.jwt_algorithm = TEST_ALGORITHM
    cfg.settings.orchestrator_url = "http://orchestrator:8001"

    from main import app

    with TestClient(app) as client:
        response = client.get(f"/api/v1/sse/{uuid.uuid4()}")

    assert response.status_code == 422  # FastAPI Query(...) required
