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
        "src/pages/RepoExplorer.jsx",
        "src/pages/QueryInterface.jsx",
        "src/components/FileTree.jsx",
        "src/components/CodeViewer.jsx",
        "src/components/QueryInput.jsx",
        "src/components/AnswerDisplay.jsx",
        "src/components/CitationLink.jsx",
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
    assert "<RepoExplorer />" in app
    assert "<QueryInterface />" in app
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


def test_repository_explorer_supports_tree_code_and_line_highlighting() -> None:
    explorer = read("src/pages/RepoExplorer.jsx")
    file_tree = read("src/components/FileTree.jsx")
    code_viewer = read("src/components/CodeViewer.jsx")

    assert "apiFetch(`/api/v1/repos/${id}/tree`)" in explorer
    assert "FileTree" in explorer
    assert "CodeViewer" in explorer
    assert "buildTree(files)" in file_tree
    assert "expanded" in file_tree
    assert "highlightSyntax" in code_viewer
    assert "lineNumber >= range.start" in code_viewer
    assert "python" in code_viewer
    assert "javascript" in code_viewer
    assert "typescript" in code_viewer


def test_query_interface_supports_chat_citations_and_history() -> None:
    query_interface = read("src/pages/QueryInterface.jsx")
    query_input = read("src/components/QueryInput.jsx")
    answer_display = read("src/components/AnswerDisplay.jsx")
    citation_link = read("src/components/CitationLink.jsx")

    assert 'apiFetch("/api/v1/query"' in query_interface
    assert "repository_id: repositoryId || null" in query_interface
    assert "Session history" in query_interface
    assert "Searching code, graph, and citations" in query_interface
    assert "onSubmit={submitQuery}" in query_interface
    assert "disabled={disabled}" in query_input
    assert "AnswerDisplay" in query_interface
    assert "CITATION_PATTERN" in answer_display
    assert "CitationLink" in answer_display
    assert "parseCitationMarker" in citation_link
    assert "file: parsed.filePath" in citation_link
    assert "lines: `${parsed.startLine}-${parsed.endLine}`" in citation_link
    assert "to={`/repos/${repositoryId}?${search.toString()}`}" in citation_link
