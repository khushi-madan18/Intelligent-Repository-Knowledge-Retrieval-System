"""Google OAuth 2.0 authentication routes."""

from __future__ import annotations

import asyncio
import json
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Protocol

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.reporag.api.middleware.auth import (
    JWTError,
    create_access_token,
    create_refresh_token,
    get_current_user,
    validate_refresh_token,
)
from src.reporag.config import settings
from src.reporag.db.models import User
from src.reporag.db.session import get_db

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"
GOOGLE_SCOPES = "openid email profile"

router = APIRouter(prefix="/auth", tags=["auth"])


class GoogleOAuthClient(Protocol):
    """Interface for exchanging Google OAuth code and loading profile data."""

    def build_authorization_url(
        self, redirect_uri: str, state: str | None = None
    ) -> str:
        """Return Google consent-screen URL."""

    async def exchange_code(self, code: str, redirect_uri: str) -> dict[str, Any]:
        """Exchange authorization code for provider tokens."""

    async def fetch_userinfo(self, access_token: str) -> dict[str, Any]:
        """Fetch Google user info for an access token."""


@dataclass(frozen=True)
class GoogleOAuthHTTPClient:
    """Google OAuth client using stdlib HTTP calls."""

    client_id: str | None = None
    client_secret: str | None = None

    def build_authorization_url(
        self, redirect_uri: str, state: str | None = None
    ) -> str:
        client_id = self.client_id or settings.google_client_id
        if not client_id:
            raise OAuthConfigurationError("GOOGLE_CLIENT_ID is not configured")

        params = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": GOOGLE_SCOPES,
            "access_type": "offline",
            "prompt": "consent",
        }
        if state:
            params["state"] = state
        return f"{GOOGLE_AUTH_URL}?{urllib.parse.urlencode(params)}"

    async def exchange_code(self, code: str, redirect_uri: str) -> dict[str, Any]:
        client_id = self.client_id or settings.google_client_id
        client_secret = self.client_secret or (
            settings.google_client_secret.get_secret_value()
            if settings.google_client_secret is not None
            else None
        )
        if not client_id or not client_secret:
            raise OAuthConfigurationError("Google OAuth client credentials are missing")

        payload = urllib.parse.urlencode(
            {
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            }
        ).encode()
        return await asyncio.to_thread(
            _post_json,
            GOOGLE_TOKEN_URL,
            payload,
            {"Content-Type": "application/x-www-form-urlencoded"},
        )

    async def fetch_userinfo(self, access_token: str) -> dict[str, Any]:
        return await asyncio.to_thread(
            _get_json,
            GOOGLE_USERINFO_URL,
            {"Authorization": f"Bearer {access_token}"},
        )


class OAuthConfigurationError(RuntimeError):
    """Raised when OAuth settings are incomplete."""


class AuthUserResponse(BaseModel):
    """Authenticated user summary."""

    id: str
    email: str
    display_name: str | None = None
    provider: str | None = None
    provider_user_id: str | None = None


class TokenResponse(BaseModel):
    """JWT response returned after successful OAuth login."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: AuthUserResponse


class RefreshRequest(BaseModel):
    """Refresh token request."""

    refresh_token: str


class RefreshResponse(BaseModel):
    """Token refresh response."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


@router.get("/google", status_code=307)
async def google_login(request: Request, state: str | None = None) -> RedirectResponse:
    """Redirect the user to the Google OAuth consent screen."""

    client = _oauth_client(request)
    redirect_uri = _callback_url(request)
    try:
        authorization_url = client.build_authorization_url(redirect_uri, state=state)
    except OAuthConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc
    return RedirectResponse(authorization_url)


@router.get("/google/callback", response_model=TokenResponse)
async def google_callback(
    request: Request,
    code: str | None = None,
    error: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """Exchange Google OAuth code, upsert user, and return JWTs."""

    if error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error)
    if not code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing OAuth authorization code",
        )

    client = _oauth_client(request)
    redirect_uri = _callback_url(request)
    try:
        provider_tokens = await client.exchange_code(code, redirect_uri)
        google_access_token = provider_tokens["access_token"]
        userinfo = await client.fetch_userinfo(google_access_token)
    except OAuthConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc
    except (KeyError, RuntimeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Google OAuth failed: {exc}",
        ) from exc

    user = await upsert_google_user(db, userinfo)
    claims = {"email": user.email, "roles": ["user"], "provider": "google"}
    return TokenResponse(
        access_token=create_access_token(user.id, **claims),
        refresh_token=create_refresh_token(user.id, **claims),
        user=AuthUserResponse(
            id=user.id,
            email=user.email,
            display_name=user.display_name,
            provider=user.provider,
            provider_user_id=user.provider_user_id,
        ),
    )


@router.post("/refresh", response_model=RefreshResponse)
async def refresh_tokens(request: RefreshRequest) -> RefreshResponse:
    """Issue fresh JWTs from a valid refresh token."""

    try:
        claims = validate_refresh_token(request.refresh_token)
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc

    user_id = str(claims.get("user_id") or claims.get("sub") or "")
    email = str(claims.get("email") or "")
    roles = claims.get("roles")
    if not user_id or not email or not isinstance(roles, list):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token is missing required claims",
        )

    token_claims = {
        "email": email,
        "roles": [str(role) for role in roles],
        "provider": claims.get("provider"),
    }
    return RefreshResponse(
        access_token=create_access_token(user_id, **token_claims),
        refresh_token=create_refresh_token(user_id, **token_claims),
    )


@router.get("/me", response_model=AuthUserResponse)
async def read_current_user(user: User = Depends(get_current_user)) -> AuthUserResponse:
    """Return the authenticated user for a valid bearer token."""

    return AuthUserResponse(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        provider=user.provider,
        provider_user_id=user.provider_user_id,
    )


async def upsert_google_user(db: AsyncSession, userinfo: dict[str, Any]) -> User:
    """Create or update a User record from Google profile data."""

    email = userinfo.get("email")
    provider_user_id = userinfo.get("sub")
    if not email or not provider_user_id:
        raise ValueError("Google profile is missing email or subject")

    result = await db.execute(
        select(User).where(
            (User.provider == "google") & (User.provider_user_id == provider_user_id)
        )
    )
    user = result.scalar_one_or_none()
    if user is None:
        email_result = await db.execute(select(User).where(User.email == email))
        user = email_result.scalar_one_or_none()

    if user is None:
        user = User(email=email)
        db.add(user)

    user.email = email
    user.display_name = userinfo.get("name")
    user.provider = "google"
    user.provider_user_id = provider_user_id
    user.is_active = True
    await db.commit()
    await db.refresh(user)
    return user


def _oauth_client(request: Request) -> GoogleOAuthClient:
    client = getattr(request.app.state, "google_oauth_client", None)
    return client or GoogleOAuthHTTPClient()


def _callback_url(request: Request) -> str:
    return str(request.url_for("google_callback"))


def _post_json(url: str, data: bytes, headers: dict[str, str]) -> dict[str, Any]:
    request = urllib.request.Request(url, data=data, headers=headers, method="POST")
    return _load_json(request)


def _get_json(url: str, headers: dict[str, str]) -> dict[str, Any]:
    request = urllib.request.Request(url, headers=headers, method="GET")
    return _load_json(request)


def _load_json(request: urllib.request.Request) -> dict[str, Any]:
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.loads(response.read().decode())
    except OSError as exc:
        raise RuntimeError(str(exc)) from exc
