"""
Unit tests for services/gateway/middleware/rate_limit.py.

All Redis calls are mocked. Tests run in isolation — no containers required.

Run:
    cd nexus
    python -m pytest services/gateway/tests/test_rate_limit.py -v --asyncio-mode=auto
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from starlette.requests import Request
from starlette.responses import Response

# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_mock_request(
    path: str = "/api/v1/runs",
    user_id: str | None = "user-abc-123",
    client_host: str = "127.0.0.1",
) -> MagicMock:
    """Build a mock Starlette Request with configurable state."""
    request = MagicMock(spec=Request)
    request.url.path = path
    request.headers = {}

    if user_id:
        request.state.current_user = {"user_id": user_id, "jti": "jti-xyz"}
    else:
        # Simulate unauthenticated — no current_user attribute
        del request.state.current_user

    mock_client = MagicMock()
    mock_client.host = client_host
    request.client = mock_client
    return request


def _make_redis(incr_return: int = 1) -> AsyncMock:
    """Return a mock Redis client with controllable INCR response."""
    redis = AsyncMock()
    redis.incr = AsyncMock(return_value=incr_return)
    redis.expire = AsyncMock(return_value=True)
    return redis


# ── Tests ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_request_within_limit_passes_through() -> None:
    """Request #1 of 60 passes through and sets X-RateLimit headers."""
    from middleware.rate_limit import RateLimitMiddleware

    redis = _make_redis(incr_return=1)
    request = _make_mock_request()
    request.app.state.redis = redis

    async def call_next(req: Request) -> Response:
        return Response("ok", status_code=200)

    middleware = RateLimitMiddleware(app=MagicMock())
    response = await middleware.dispatch(request, call_next)

    assert response.status_code == 200
    assert response.headers["X-RateLimit-Limit"] == "60"
    assert response.headers["X-RateLimit-Remaining"] == "59"


@pytest.mark.asyncio
async def test_request_at_limit_boundary_passes() -> None:
    """Request #60 (count == limit) still passes through."""
    from middleware.rate_limit import RateLimitMiddleware

    redis = _make_redis(incr_return=60)
    request = _make_mock_request()
    request.app.state.redis = redis

    async def call_next(req: Request) -> Response:
        return Response("ok", status_code=200)

    middleware = RateLimitMiddleware(app=MagicMock())
    response = await middleware.dispatch(request, call_next)

    assert response.status_code == 200
    assert response.headers["X-RateLimit-Remaining"] == "0"


@pytest.mark.asyncio
async def test_request_over_limit_returns_429() -> None:
    """Request #61 (count > limit) returns 429 with Retry-After header."""
    from middleware.rate_limit import RateLimitMiddleware

    redis = _make_redis(incr_return=61)
    request = _make_mock_request()
    request.app.state.redis = redis

    call_next_called = False

    async def call_next(req: Request) -> Response:
        nonlocal call_next_called
        call_next_called = True
        return Response("ok", status_code=200)

    middleware = RateLimitMiddleware(app=MagicMock())
    response = await middleware.dispatch(request, call_next)

    assert response.status_code == 429
    assert call_next_called is False
    assert "Retry-After" in response.headers
    assert int(response.headers["Retry-After"]) >= 1
    assert response.headers["X-RateLimit-Limit"] == "60"
    assert response.headers["X-RateLimit-Remaining"] == "0"


@pytest.mark.asyncio
async def test_redis_expire_called_on_first_request() -> None:
    """EXPIRE is called when INCR returns 1 (first request in window)."""
    from middleware.rate_limit import RateLimitMiddleware

    redis = _make_redis(incr_return=1)
    request = _make_mock_request()
    request.app.state.redis = redis

    async def call_next(req: Request) -> Response:
        return Response("ok", status_code=200)

    middleware = RateLimitMiddleware(app=MagicMock())
    await middleware.dispatch(request, call_next)

    redis.expire.assert_awaited_once()
    args = redis.expire.call_args[0]
    assert args[1] == 60  # TTL must be 60 seconds


@pytest.mark.asyncio
async def test_redis_expire_not_called_on_subsequent_requests() -> None:
    """EXPIRE is NOT called when INCR returns > 1 (subsequent requests)."""
    from middleware.rate_limit import RateLimitMiddleware

    redis = _make_redis(incr_return=5)
    request = _make_mock_request()
    request.app.state.redis = redis

    async def call_next(req: Request) -> Response:
        return Response("ok", status_code=200)

    middleware = RateLimitMiddleware(app=MagicMock())
    await middleware.dispatch(request, call_next)

    redis.expire.assert_not_awaited()


@pytest.mark.asyncio
async def test_redis_failure_fails_open() -> None:
    """Redis error causes fail-open: request passes through without rate limiting."""
    from middleware.rate_limit import RateLimitMiddleware

    redis = AsyncMock()
    redis.incr = AsyncMock(side_effect=Exception("Redis connection refused"))

    request = _make_mock_request()
    request.app.state.redis = redis

    call_next_called = False

    async def call_next(req: Request) -> Response:
        nonlocal call_next_called
        call_next_called = True
        return Response("ok", status_code=200)

    middleware = RateLimitMiddleware(app=MagicMock())
    response = await middleware.dispatch(request, call_next)

    assert response.status_code == 200
    assert call_next_called is True


@pytest.mark.asyncio
async def test_unauthenticated_request_uses_ip_as_identifier() -> None:
    """Requests without current_user fall back to client IP for rate limiting."""
    from middleware.rate_limit import RateLimitMiddleware

    redis = _make_redis(incr_return=1)

    # Build request without current_user
    request = MagicMock(spec=Request)
    request.url.path = "/healthz"
    request.headers = {}
    request.state = MagicMock(spec=[])  # no current_user attribute
    mock_client = MagicMock()
    mock_client.host = "10.0.0.1"
    request.client = mock_client
    request.app.state.redis = redis

    async def call_next(req: Request) -> Response:
        return Response("ok", status_code=200)

    middleware = RateLimitMiddleware(app=MagicMock())
    response = await middleware.dispatch(request, call_next)

    assert response.status_code == 200
    # Verify the Redis key contains the IP, not a user_id
    incr_call_key: str = redis.incr.call_args[0][0]
    assert "10.0.0.1" in incr_call_key


@pytest.mark.asyncio
async def test_rate_limit_key_includes_user_id_and_minute_epoch() -> None:
    """Redis key pattern is ratelimit:{user_id}:{minute_epoch}."""
    import time

    from middleware.rate_limit import RateLimitMiddleware

    redis = _make_redis(incr_return=1)
    user_id = "user-abc-123"
    request = _make_mock_request(user_id=user_id)
    request.app.state.redis = redis

    async def call_next(req: Request) -> Response:
        return Response("ok", status_code=200)

    middleware = RateLimitMiddleware(app=MagicMock())
    await middleware.dispatch(request, call_next)

    incr_call_key: str = redis.incr.call_args[0][0]
    expected_epoch = int(time.time() // 60)
    assert incr_call_key == f"ratelimit:{user_id}:{expected_epoch}"


@pytest.mark.asyncio
async def test_x_forwarded_for_used_when_present() -> None:
    """X-Forwarded-For header is used as identifier over client.host."""
    from middleware.rate_limit import RateLimitMiddleware

    redis = _make_redis(incr_return=1)

    request = MagicMock(spec=Request)
    request.url.path = "/healthz"
    request.headers = {"X-Forwarded-For": "203.0.113.42, 10.0.0.1"}
    request.state = MagicMock(spec=[])
    mock_client = MagicMock()
    mock_client.host = "10.0.0.1"
    request.client = mock_client
    request.app.state.redis = redis

    async def call_next(req: Request) -> Response:
        return Response("ok", status_code=200)

    middleware = RateLimitMiddleware(app=MagicMock())
    await middleware.dispatch(request, call_next)

    incr_call_key: str = redis.incr.call_args[0][0]
    # First IP in X-Forwarded-For chain should be used
    assert "203.0.113.42" in incr_call_key
