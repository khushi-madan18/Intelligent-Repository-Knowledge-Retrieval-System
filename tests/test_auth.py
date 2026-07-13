"""Tests for Google OAuth authentication flow."""

from __future__ import annotations

import asyncio

from starlette.requests import Request

from src.reporag.api.main import create_app
from src.reporag.api.middleware.auth import (
    create_access_token,
    create_refresh_token,
    decode_jwt_token,
    get_current_user,
    require_bearer_token,
)
from src.reporag.api.routes.auth import (
    RefreshRequest,
    google_callback,
    google_login,
    refresh_tokens,
)
from src.reporag.db.models import User


class FakeGoogleOAuthClient:
    def __init__(self) -> None:
        self.exchanged_code: str | None = None

    def build_authorization_url(
        self, redirect_uri: str, state: str | None = None
    ) -> str:
        return f"https://accounts.google.com/o/oauth2/v2/auth?redirect_uri={redirect_uri}&state={state or ''}"

    async def exchange_code(self, code: str, redirect_uri: str) -> dict[str, str]:
        self.exchanged_code = code
        return {"access_token": "google-access-token"}

    async def fetch_userinfo(self, access_token: str) -> dict[str, str]:
        return {
            "sub": "google-user-1",
            "email": "khushi@example.com",
            "name": "Khushi",
        }


class FakeScalarResult:
    def __init__(self, user: User | None) -> None:
        self.user = user

    def scalar_one_or_none(self) -> User | None:
        return self.user


class FakeSession:
    def __init__(self, users: list[User] | None = None) -> None:
        self.users = users or []
        self.execute_calls = 0

    async def execute(self, statement: object) -> FakeScalarResult:
        self.execute_calls += 1
        if len(self.users) == 1 and self.users[0].id == "user-1":
            return FakeScalarResult(self.users[0])

        if self.execute_calls % 2 == 1:
            user = next(
                (
                    existing
                    for existing in self.users
                    if existing.provider == "google"
                    and existing.provider_user_id == "google-user-1"
                ),
                None,
            )
            return FakeScalarResult(user)

        user = next(
            (
                existing
                for existing in self.users
                if existing.email == "khushi@example.com"
            ),
            None,
        )
        return FakeScalarResult(user)

    def add(self, user: User) -> None:
        if user.id is None:
            user.id = f"user-{len(self.users) + 1}"
        self.users.append(user)

    async def commit(self) -> None:
        return None

    async def refresh(self, user: User) -> None:
        if user.id is None:
            user.id = f"user-{len(self.users) + 1}"


def request_for(path: str = "/auth/google") -> Request:
    app = create_app()
    app.state.google_oauth_client = FakeGoogleOAuthClient()
    scope = {
        "type": "http",
        "method": "GET",
        "path": path,
        "headers": [],
        "scheme": "http",
        "server": ("testserver", 80),
        "client": ("testclient", 50000),
        "root_path": "",
        "app": app,
        "router": app.router,
    }
    return Request(scope)


def test_google_login_redirects_to_consent_screen() -> None:
    response = asyncio.run(google_login(request_for(), state="csrf-token"))

    assert response.status_code == 307
    assert response.headers["location"].startswith(
        "https://accounts.google.com/o/oauth2/v2/auth"
    )
    assert "state=csrf-token" in response.headers["location"]


def test_google_callback_creates_user_and_returns_jwt_tokens() -> None:
    async def run() -> tuple[str, str, int]:
        session = FakeSession()
        response = await google_callback(
            request_for("/auth/google/callback"),
            code="oauth-code",
            db=session,
        )
        return response.access_token, response.user.email, len(session.users)

    access_token, email, user_count = asyncio.run(run())
    claims = decode_jwt_token(access_token)

    assert claims["sub"]
    assert claims["user_id"] == claims["sub"]
    assert claims["type"] == "access"
    assert claims["email"] == "khushi@example.com"
    assert claims["roles"] == ["user"]
    assert email == "khushi@example.com"
    assert user_count == 1


def test_google_callback_updates_existing_user() -> None:
    async def run() -> str:
        session = FakeSession(
            [
                User(
                    id="user-1",
                    email="khushi@example.com",
                    display_name="Old Name",
                    provider="google",
                    provider_user_id="google-user-1",
                )
            ]
        )
        response = await google_callback(
            request_for("/auth/google/callback"),
            code="oauth-code",
            db=session,
        )
        return response.user.display_name or ""

    assert asyncio.run(run()) == "Khushi"


def test_google_callback_handles_oauth_error() -> None:
    async def run() -> int:
        try:
            await google_callback(
                request_for("/auth/google/callback"),
                error="access_denied",
                db=FakeSession(),
            )
        except Exception as exc:
            return getattr(exc, "status_code", 0)
        raise AssertionError("OAuth error was not raised")

    assert asyncio.run(run()) == 400


def test_jwt_round_trip_verifies_claims() -> None:
    token = create_access_token(
        "user-1",
        email="khushi@example.com",
        roles=["admin"],
    )

    claims = decode_jwt_token(token)

    assert claims["sub"] == "user-1"
    assert claims["user_id"] == "user-1"
    assert claims["type"] == "access"
    assert claims["email"] == "khushi@example.com"
    assert claims["roles"] == ["admin"]
    assert isinstance(claims["iat"], int)
    assert isinstance(claims["exp"], int)


def test_protected_dependency_returns_401_without_token() -> None:
    try:
        require_bearer_token(None)
    except Exception as exc:
        assert getattr(exc, "status_code", 0) == 401
    else:
        raise AssertionError("Missing bearer token should fail")


def test_refresh_endpoint_issues_new_tokens() -> None:
    refresh_token = create_refresh_token(
        "user-1",
        email="khushi@example.com",
        roles=["user"],
    )

    response = asyncio.run(refresh_tokens(RefreshRequest(refresh_token=refresh_token)))
    access_claims = decode_jwt_token(response.access_token)
    refresh_claims = decode_jwt_token(response.refresh_token)

    assert access_claims["type"] == "access"
    assert refresh_claims["type"] == "refresh"
    assert access_claims["user_id"] == "user-1"
    assert access_claims["email"] == "khushi@example.com"


def test_refresh_endpoint_rejects_access_token() -> None:
    access_token = create_access_token("user-1", email="khushi@example.com")

    try:
        asyncio.run(refresh_tokens(RefreshRequest(refresh_token=access_token)))
    except Exception as exc:
        assert getattr(exc, "status_code", 0) == 401
    else:
        raise AssertionError("Access token should not refresh")


def test_get_current_user_dependency_returns_active_user() -> None:
    user = User(
        id="user-1",
        email="khushi@example.com",
        display_name="Khushi",
        provider="google",
        provider_user_id="google-user-1",
        is_active=True,
    )
    claims = decode_jwt_token(create_access_token("user-1", email=user.email))

    current_user = asyncio.run(get_current_user(claims, FakeSession([user])))

    assert current_user.email == "khushi@example.com"
