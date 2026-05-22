"""Unit tests for services/gateway/routers/auth.py.

All external dependencies (DB, Redis) are mocked via pytest-mock.
Tests run in isolation — no Docker containers required.

docker exec  -it <container_id> python -m pytest tests/ -v --asyncio-mode=auto
docker exec -it 7d36833c7367 python -m pytest tests/ -v --asyncio-mode=auto
"""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from jose import jwt

# Patch settings before importing the app to control SECRET_KEY etc.
TEST_SECRET = "test-secret-key-exactly-32-chars!!"


@pytest.fixture(autouse=True)
def patch_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Override settings for all tests in this module."""
    monkeypatch.setenv("JWT_SECRET_KEY", TEST_SECRET)
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://x:x@localhost/x")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")


@pytest.fixture()
def mock_db_session() -> AsyncMock:
    """Return a mock async SQLAlchemy session."""
    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    return session


@pytest.fixture()
def mock_redis() -> AsyncMock:
    """Return a mock async Redis client."""
    redis = AsyncMock()
    redis.set = AsyncMock(return_value=True)
    redis.exists = AsyncMock(return_value=1)
    return redis


# ---------------------------------------------------------------------------
# Register tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_register_success(mock_db_session: AsyncMock, mock_redis: AsyncMock) -> None:
    """POST /register with valid payload returns 201 with user fields."""
    from routers.auth import register, RegisterRequest

    # Simulate no existing user (duplicate check returns None)
    mock_result = MagicMock()
    mock_result.fetchone.return_value = None
    mock_db_session.execute = AsyncMock(return_value=mock_result)

    request = RegisterRequest(
        display_name="testuser",
        email="test@nexus.dev",
        password="Test1234!",
    )
    response = await register(body=request, db=mock_db_session)

    assert response.display_name == "testuser"
    assert response.email == "test@nexus.dev"
    assert uuid.UUID(response.user_id)  # valid UUID
    mock_db_session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_register_duplicate_email_returns_409(mock_db_session: AsyncMock) -> None:
    """POST /register with existing email raises 409 HTTPException."""
    from fastapi import HTTPException
    from routers.auth import register, RegisterRequest

    # Simulate existing user found
    mock_result = MagicMock()
    mock_result.fetchone.return_value = MagicMock()  # non-None → duplicate
    mock_db_session.execute = AsyncMock(return_value=mock_result)

    request = RegisterRequest(
        display_name="testuser",
        email="existing@nexus.dev",
        password="Test1234!",
    )

    with pytest.raises(HTTPException) as exc_info:
        await register(body=request, db=mock_db_session)

    assert exc_info.value.status_code == status.HTTP_409_CONFLICT
    assert "already registered" in exc_info.value.detail


# ---------------------------------------------------------------------------
# Login tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_login_success_returns_token(
    mock_db_session: AsyncMock,
    mock_redis: AsyncMock,
) -> None:
    """POST /login with valid credentials returns TokenResponse with correct fields."""
    from routers.auth import login, LoginRequest, _hash_password

    hashed = _hash_password("Test1234!")
    mock_row = MagicMock()
    mock_row.id = str(uuid.uuid4())
    mock_row.display_name = "testuser"
    mock_row.password_hash = hashed

    mock_result = MagicMock()
    mock_result.fetchone.return_value = mock_row
    mock_db_session.execute = AsyncMock(return_value=mock_result)

    request = LoginRequest(email="test@nexus.dev", password="Test1234!")
    response = await login(body=request, db=mock_db_session, redis=mock_redis)

    assert response.token_type == "bearer"
    assert response.expires_in == 86400
    assert len(response.access_token) > 20
    mock_redis.set.assert_awaited_once()


@pytest.mark.asyncio
async def test_login_wrong_password_returns_401(
    mock_db_session: AsyncMock,
    mock_redis: AsyncMock,
) -> None:
    """POST /login with wrong password raises 401 HTTPException."""
    from fastapi import HTTPException
    from routers.auth import login, LoginRequest, _hash_password

    hashed = _hash_password("CorrectPassword!")
    mock_row = MagicMock()
    mock_row.password_hash = hashed

    mock_result = MagicMock()
    mock_result.fetchone.return_value = mock_row
    mock_db_session.execute = AsyncMock(return_value=mock_result)

    request = LoginRequest(email="test@nexus.dev", password="WrongPassword!")

    with pytest.raises(HTTPException) as exc_info:
        await login(body=request, db=mock_db_session, redis=mock_redis)

    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.asyncio
async def test_login_nonexistent_email_returns_401(
    mock_db_session: AsyncMock,
    mock_redis: AsyncMock,
) -> None:
    """POST /login with unknown email raises 401 HTTPException."""
    from fastapi import HTTPException
    from routers.auth import login, LoginRequest

    mock_result = MagicMock()
    mock_result.fetchone.return_value = None  # user not found
    mock_db_session.execute = AsyncMock(return_value=mock_result)

    request = LoginRequest(email="ghost@nexus.dev", password="Test1234!")

    with pytest.raises(HTTPException) as exc_info:
        await login(body=request, db=mock_db_session, redis=mock_redis)

    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.asyncio
async def test_login_redis_failure_returns_503(
    mock_db_session: AsyncMock,
) -> None:
    """POST /login raises 503 when Redis session write fails."""
    from fastapi import HTTPException
    from routers.auth import login, LoginRequest, _hash_password

    hashed = _hash_password("Test1234!")
    mock_row = MagicMock()
    mock_row.id = str(uuid.uuid4())
    mock_row.display_name = "testuser"
    mock_row.password_hash = hashed

    mock_result = MagicMock()
    mock_result.fetchone.return_value = mock_row
    mock_db_session.execute = AsyncMock(return_value=mock_result)

    failing_redis = AsyncMock()
    failing_redis.set = AsyncMock(side_effect=Exception("Redis connection refused"))

    request = LoginRequest(email="test@nexus.dev", password="Test1234!")

    with pytest.raises(HTTPException) as exc_info:
        await login(body=request, db=mock_db_session, redis=failing_redis)

    assert exc_info.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE


# ---------------------------------------------------------------------------
# JWT helper tests
# ---------------------------------------------------------------------------


def test_create_access_token_contains_required_claims() -> None:
    """_create_access_token returns token with sub, jti, iat, exp, and display_name claims."""
    import importlib
    import config as cfg

    original_secret = cfg.settings.jwt_secret_key
    cfg.settings.jwt_secret_key = TEST_SECRET

    from routers.auth import _create_access_token

    user_id = str(uuid.uuid4())
    token, jti = _create_access_token(user_id, display_name="Test User")

    payload = jwt.decode(token, TEST_SECRET, algorithms=["HS256"])
    assert payload["sub"] == user_id
    assert payload["jti"] == jti
    assert payload["display_name"] == "Test User"
    assert "iat" in payload
    assert "exp" in payload

    cfg.settings.jwt_secret_key = original_secret


def test_hash_and_verify_password_roundtrip() -> None:
    """_hash_password and _verify_password form a consistent roundtrip."""
    from routers.auth import _hash_password, _verify_password

    plain = "MySecurePassword123!"
    hashed = _hash_password(plain)
    assert hashed != plain
    assert _verify_password(plain, hashed) is True
    assert _verify_password("WrongPassword", hashed) is False