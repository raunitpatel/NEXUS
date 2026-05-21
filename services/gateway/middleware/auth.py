"""
JWT Bearer authentication middleware for the API Gateway.

Validates every inbound request except auth routes and health checks.
On success, injects current_user into request.state for downstream handlers.
On failure, returns 401 immediately without forwarding to the route handler.

Session validation is two-factor:
  1. JWT signature and expiry (python-jose)
  2. Redis session key existence (session:{jti}) — enables server-side revocation
"""

import structlog
from jose import JWTError, jwt
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

from config import settings

logger = structlog.get_logger(__name__)

_EXEMPT_PREFIXES: tuple[str, ...] = (
    "/api/v1/auth/",
    "/healthz",
    "/metrics",
    "/docs",
    "/openapi.json",
    "/api/v1/sse/"
)

class AuthMiddleware(BaseHTTPMiddleware):
    """
    Starlette middleware that validates JWT Bearer tokens on every request.

    Uses python-jose for JWT decoding and Redis for session existence check.
    Adds current_user to request.state on success.
    """

    def __init__(self, app: ASGIApp) -> None:
        """Initialise middleware with the ASGI app."""
        super().__init__(app)

    async def dispatch(self, request: Request, call_next:object) -> Response:
        """
        Intercept every request to validate auth before forwarding.

        Args:
            request: The incoming Starlette request.
            call_next: The next ASGI handler in the chain.

        Returns:
            401 JSONResponse on auth failure, or the downstream response on success.
        """
        # Exempt paths bypass auth entirely
        path: str = request.url.path
        if any(path.startswith(prefix) for prefix in _EXEMPT_PREFIXES):
            return await call_next(request)
        
        # Extract Bearer token
        authorization: str | None = request.headers.get("Authorization")
        if not authorization or not authorization.startswith("Bearer "):
            return JSONResponse(
                status_code=401,
                content={"detail": "Not authenticated"},
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        token: str = authorization.removeprefix("Bearer ").strip()

        # Validate JWT signature and expiry
        try:
            payload = jwt.decode(
                token,
                settings.jwt_secret_key,
                algorithms=[settings.jwt_algorithm],
            )
        except JWTError:
            logger.warning("auth.jwt_invalid", path=path)
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid token or expired token"},
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        jti: str | None = payload.get("jti")
        user_id: str | None = payload.get("sub")

        if not jti or not user_id:
            logger.warning("auth.jwt_missing_claims", path=path)
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid token claims"},
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # Validate session exists in Redis (catches revoked tokens)
        try:
            redis = request.app.state.redis
            session_exists = await redis.exists(f"session:{jti}")
        except Exception as exc:
            logger.error("auth.redis_error", path=path, error=str(exc))
            return JSONResponse(
                status_code=503,
                content={"detail": "Authentication service unavailable"},
            )
        
        if not session_exists:
            logger.info("auth.session_not_found", path=path, jti=jti)
            return JSONResponse(
                status_code=401,
                content={"detail": "Session expired or revoked"},
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # Inject current_user into request.state for downstream route handlers
        request.state.current_user = {"user_id": user_id, "jti": jti}
        return await call_next(request)