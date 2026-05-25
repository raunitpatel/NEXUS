"""
Authentication router for the API Gateway.

Provides:
  POST /api/v1/auth/register  — create new user account
  POST /api/v1/auth/login     — exchange credentials for JWT

Both endpoints are exempt from AuthMiddleware (see middleware/auth.py _EXEMPT_PREFIXES).
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

import structlog
from config import settings
from dependencies import get_db_session, get_redis
from fastapi import APIRouter, Depends, HTTPException, status
from jose import jwt
from passlib.context import CryptContext
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)
router = APIRouter()

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Pydantic request / response models


class RegisterRequest(BaseModel):
    """Payload for POST /api/v1/auth/register."""

    display_name: str | None = Field(default=None, max_length=100)
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)


class RegisterResponse(BaseModel):
    """Response returned on successful registration."""

    user_id: str
    display_name: str | None
    email: str


class LoginRequest(BaseModel):
    """Payload for POST /api/v1/auth/login."""

    email: EmailStr
    password: str = Field(..., min_length=1)


class TokenResponse(BaseModel):
    """JWT token response returned on successful login."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int = settings.access_token_expire_seconds


# Helper functions


def _hash_password(plain: str) -> str:
    """
    Hash a plaintext password using bcrypt.

    Args:
        plain: The plaintext password from the registration request.

    Returns:
        bcrypt hash string suitable for storage in the users table.
    """
    return _pwd_context.hash(plain)


def _verify_password(plain: str, hashed: str) -> bool:
    """
    Verify a plaintext password against a bcrypt hash.

    Args:
        plain: Plaintext password from the login request.
        hashed: bcrypt hash stored in the users table.

    Returns:
        True if the password matches, False otherwise.
    """
    return _pwd_context.verify(plain, hashed)


def _create_access_token(user_id: str, display_name: str | None = None) -> tuple[str, str]:
    """
    Create a signed JWT access token for the given user.

    Args:
        user_id: The UUID string of the authenticated user.
        display_name: Optional display name to include in the token payload.

    Returns:
        Tuple of (encoded_jwt, jti) where jti is the unique token identifier
        used as the Redis session key suffix.
    """
    jti = str(uuid.uuid4())
    now = datetime.now(tz=UTC)
    expire = now + timedelta(seconds=settings.access_token_expire_seconds)
    payload = {
        "sub": user_id,
        "jti": jti,
        "iat": now,
        "exp": expire,
    }
    if display_name is not None:
        payload["display_name"] = display_name

    token = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    return token, jti


# Endpoints


@router.post(
    "/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new Nexus user account",
)
async def register(
    body: RegisterRequest,
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> RegisterResponse:
    """
    Create a new user account.

    Checks for duplicate email (returns 409) before inserting into the users table.
    Password is hashed with bcrypt before storage — the plaintext is never persisted.

    Args:
        body: Registration payload with display_name, email, and password.
        db: Injected async SQLAlchemy session.

    Returns:
        RegisterResponse with the new user's id, display_name, and email.

    Raises:
        HTTPException 409: If the email is already registered.
    """

    # Checking for duplicate mail
    result = await db.execute(
        text("SELECT id FROM users WHERE email = :email"),
        {"email": body.email},
    )

    existing = result.fetchone()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    # Insert new user
    user_id = str(uuid.uuid4())
    hashed = _hash_password(body.password)

    await db.execute(
        text(
            """
            INSERT INTO users (id, display_name, email, password_hash, created_at)
            VALUES (:id, :display_name, :email, :password_hash, NOW())
            """
        ),
        {
            "id": user_id,
            "display_name": body.display_name,
            "email": body.email,
            "password_hash": hashed,
        },
    )
    await db.commit()

    logger.info("auth.register_success", user_id=user_id, email=body.email)
    return RegisterResponse(user_id=user_id, display_name=body.display_name, email=body.email)


@router.post(
    "/login",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Exchange credentials for a JWT access token",
)
async def login(
    body: LoginRequest,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    redis=Depends(get_redis),
) -> TokenResponse:
    """
    Authenticate a user and return a JWT access token.

    Verifies email + bcrypt password against the users table. On success,
    creates a JWT and writes the session key to Redis with a 24h TTL.
    Redis write failure causes a 503 — login cannot succeed without a session key.

    Args:
        body: Login payload with email and password.
        db: Injected async SQLAlchemy session.
        redis: Injected Redis async client.

    Returns:
        TokenResponse with access_token, token_type, and expires_in.

    Raises:
        HTTPException 401: If credentials are invalid.
        HTTPException 503: If Redis session write fails.
    """
    # Fetch user record
    result = await db.execute(
        text("SELECT id, display_name, password_hash From users WHERE email = :email"),
        {"email": body.email},
    )
    row = result.fetchone()

    if row is None or not _verify_password(body.password, row.password_hash):
        logger.warning("auth.login_failed", email=body.email)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalide email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Generate JWT, including the user's display name for client-side UI.
    token, jti = _create_access_token(user_id=str(row.id), display_name=row.display_name)

    # Write session to Redis — failure is fatal
    try:
        await redis.set(
            f"session:{jti}",
            str(row.id),
            ex=settings.access_token_expire_seconds,
        )
    except Exception as exc:
        logger.error("auth.redis_session_write_failed", error=str(exc), user_id=str(row.id))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Cache unavailable — login failed",
        )

    logger.info("auth.login_success", user_id=str(row.id))
    return TokenResponse(access_token=token)
