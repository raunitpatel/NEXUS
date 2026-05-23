"""
Redis fixed-window rate limiting middleware for the API Gateway.

Enforces a per-user (or per-IP for unauthenticated requests) request limit
using Redis INCR + EXPIRE. The window is one calendar minute.

Key pattern: ratelimit:{identifier}:{minute_epoch}
TTL:         60 seconds (set on first request in each window)

On limit exceeded: returns HTTP 429 with Retry-After header.
On Redis failure:  fails open — request is passed through with a warning log.

Response headers added on every non-429 response:
  X-RateLimit-Limit:     maximum requests per minute
  X-RateLimit-Remaining: requests remaining in current window
"""

import math
import time
from typing import Any

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

from config import settings

logger = structlog.get_logger(__name__)

class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Starlette middleware enforcing Redis-backed fixed-window rate limiting.

    Runs after AuthMiddleware so request.state.current_user is already set
    for authenticated requests. Falls back to client IP for unauthenticated
    requests on exempt paths (e.g. /healthz).

    Fails open on Redis errors to avoid taking down the API when the cache
    is temporarily unavailable.
    """

    def __init__(self, app: ASGIApp) -> None:
        """Initialise middleware with the ASGI app."""
        super().__init__(app)
        self._limit: int = settings.rate_limit_requests_per_minute

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        """
        Intercept each request to apply rate limiting before forwarding.

        Args:
            request: The incoming Starlette request.
            call_next: The next ASGI handler in the chain.

        Returns:
            HTTP 429 JSONResponse if the limit is exceeded, otherwise the
            downstream response with X-RateLimit-* headers injected.
        """

        if request.method == "OPTIONS":
            return await call_next(request)
    
        identifier = self._get_identifier(request)
        minute_epoch = int(time.time() //60)
        key = f"ratelimit:{identifier}:{minute_epoch}"

        try:
            redis = request.app.state.redis
            count: int = await redis.incr(key)
            if count == 1:
                # First request in this window - set TTL
                await redis.expire(key, 60)
        except Exception as exc:
            logger.warning(
                "rate_limit.redis_error",
                identifier=identifier,
                error=str(exc),
            )
            # Fail open: pass the request through
            return await call_next(request)
        
        remaining = max(0, self._limit - count)

        if count > self._limit:
            # Calculate seconds until the next minute window starts
            seconds_into_window = int(time.time() % 60)
            retry_after = max(1, 60 - seconds_into_window)

            logger.info(
                "rate_limit.exceeded",
                identifier=identifier,
                count=count,
                limit=self._limit,
            )
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded. Try again in a moment."},
                headers={
                    "X-RateLimit-Limit": str(self._limit),
                    "X-RateLimit-Remaining": "0",
                    "Retry-After": str(retry_after),
                },
            )
        
        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(self._limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        return response
    
    def _get_identifier(self, request: Request) -> str:
        """
        Extract the rate limit identifier from the request.

        Uses user_id from request.state.current_user if available (set by
        AuthMiddleware for authenticated requests). Falls back to the client
        IP address for unauthenticated requests on exempt paths.

        Args:
            request: The incoming Starlette request.

        Returns:
            A string identifier unique to the requester.
        """
        current_user: dict[str, str] | None = getattr(
            request.state, "current_user", None
        )
        if current_user:
            return current_user["user_id"]

        # Fallback: use X-Forwarded-For if behind NGINX, else direct client IP
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()

        if request.client:
            return request.client.host

        return "unknown"