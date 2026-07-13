"""Authentication helpers and JWT bearer middleware dependencies."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.reporag.config import settings
from src.reporag.db.models import User
from src.reporag.db.session import get_db

bearer_scheme = HTTPBearer(auto_error=False)


class JWTError(ValueError):
    """Raised when a JWT cannot be decoded or verified."""


def create_jwt_token(
    subject: str,
    *,
    token_type: str,
    expires_delta: timedelta,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    """Create a signed HS256 JWT."""

    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": subject,
        "user_id": subject,
        "type": token_type,
        "iat": int(now.timestamp()),
        "exp": int((now + expires_delta).timestamp()),
        "roles": ["user"],
    }
    payload.update(extra_claims or {})

    header = {"alg": settings.jwt_algorithm, "typ": "JWT"}
    if header["alg"] != "HS256":
        raise JWTError("Only HS256 JWT signing is supported")

    signing_input = ".".join(
        [
            _base64url_encode(json.dumps(header, separators=(",", ":")).encode()),
            _base64url_encode(json.dumps(payload, separators=(",", ":")).encode()),
        ]
    )
    signature = _sign(signing_input)
    return f"{signing_input}.{signature}"


def create_access_token(
    subject: str,
    *,
    email: str,
    roles: list[str] | None = None,
    **claims: Any,
) -> str:
    """Create an access token for an authenticated user."""

    return create_jwt_token(
        subject,
        token_type="access",
        expires_delta=timedelta(minutes=settings.access_token_expire_minutes),
        extra_claims={
            "email": email,
            "roles": roles or ["user"],
            **claims,
        },
    )


def create_refresh_token(
    subject: str,
    *,
    email: str,
    roles: list[str] | None = None,
    **claims: Any,
) -> str:
    """Create a refresh token for an authenticated user."""

    return create_jwt_token(
        subject,
        token_type="refresh",
        expires_delta=timedelta(days=settings.refresh_token_expire_days),
        extra_claims={
            "email": email,
            "roles": roles or ["user"],
            **claims,
        },
    )


def decode_jwt_token(token: str) -> dict[str, Any]:
    """Decode and verify a signed JWT."""

    parts = token.split(".")
    if len(parts) != 3:
        raise JWTError("Invalid JWT format")

    signing_input = ".".join(parts[:2])
    expected_signature = _sign(signing_input)
    if not hmac.compare_digest(parts[2], expected_signature):
        raise JWTError("Invalid JWT signature")

    try:
        header = json.loads(_base64url_decode(parts[0]))
        payload = json.loads(_base64url_decode(parts[1]))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise JWTError("Invalid JWT payload") from exc

    if header.get("alg") != "HS256":
        raise JWTError("Unsupported JWT algorithm")

    expires_at = payload.get("exp")
    if not isinstance(expires_at, int):
        raise JWTError("JWT is missing expiration")
    if datetime.now(UTC).timestamp() >= expires_at:
        raise JWTError("JWT has expired")

    return payload


def require_bearer_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> dict[str, Any]:
    """FastAPI dependency that returns verified JWT claims."""

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
        )
    try:
        claims = decode_jwt_token(credentials.credentials)
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc
    return claims


async def get_current_user(
    claims: dict[str, Any] = Depends(require_bearer_token),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Return the active user for a verified access token."""

    if claims.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Access token required",
        )

    user_id = claims.get("user_id") or claims.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="JWT is missing user_id",
        )

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )
    return user


def validate_refresh_token(token: str) -> dict[str, Any]:
    """Decode a JWT and ensure it is a refresh token."""

    claims = decode_jwt_token(token)
    if claims.get("type") != "refresh":
        raise JWTError("Refresh token required")
    return claims


def _sign(signing_input: str) -> str:
    secret = settings.jwt_secret_key.get_secret_value().encode()
    digest = hmac.new(secret, signing_input.encode(), hashlib.sha256).digest()
    return _base64url_encode(digest)


def _base64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode()


def _base64url_decode(value: str) -> str:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + padding).encode()).decode()
