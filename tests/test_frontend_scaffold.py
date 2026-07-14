"""Tests for the React/Vite frontend scaffold."""

from __future__ import annotations

import json
from pathlib import Path

FRONTEND = Path("frontend")


def read(path: str) -> str:
    return (FRONTEND / path).read_text(encoding="utf-8")


def test_frontend_package_uses_react_vite_and_tailwind() -> None:
    package = json.loads(read("package.json"))

    assert package["scripts"]["dev"] == "vite"
    assert "react" in package["dependencies"]
    assert "react-router-dom" in package["dependencies"]
    assert "vite" in package["dependencies"]
    assert "tailwindcss" in package["devDependencies"]


def test_frontend_required_files_exist() -> None:
    required_files = [
        "vite.config.js",
        "tailwind.config.js",
        "src/App.jsx",
        "src/main.jsx",
        "src/pages/Login.jsx",
        "src/pages/Dashboard.jsx",
        "src/context/AuthContext.jsx",
    ]

    for file_path in required_files:
        assert (FRONTEND / file_path).exists(), file_path


def test_routes_are_declared_with_protected_routes() -> None:
    app = read("src/App.jsx")

    for route in [
        'path="/"',
        'path="/login"',
        'path="/repos"',
        'path="/repos/:id"',
        'path="/query"',
    ]:
        assert route in app
    assert "<ProtectedRoute />" in app
    assert 'to="/login"' in read("src/components/ProtectedRoute.jsx")


def test_google_login_redirect_and_token_attachment_are_wired() -> None:
    auth_context = read("src/context/AuthContext.jsx")
    api_client = read("src/api/client.js")
    login_page = read("src/pages/Login.jsx")

    assert "window.location.assign(googleLoginUrl())" in auth_context
    assert "Continue with Google" in login_page
    assert 'headers.set("Authorization", `Bearer ${accessToken}`)' in api_client
    assert "let accessToken = null" in api_client


def test_tailwind_entrypoint_imports_tailwind_layers() -> None:
    styles = read("src/styles.css")

    assert "@tailwind base;" in styles
    assert "@tailwind components;" in styles
    assert "@tailwind utilities;" in styles
