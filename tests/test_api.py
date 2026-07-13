"""Tests for FastAPI routes."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import BackgroundTasks
from pydantic import ValidationError

from src.reporag.api.main import create_app
from src.reporag.api.routes.health import health_check
from src.reporag.api.routes.query import QueryRequest, query_repository
from src.reporag.api.routes.repos import (
    REPOSITORIES,
    RepositoryIngestRequest,
    ingest_repository,
    list_repositories,
)
from src.reporag.api.routes import repos
from src.reporag.generation.citation import Citation
from src.reporag.generation.generator import GenerationResult
from src.reporag.generation.prompt_builder import BuiltPrompt


class FakeManifestEntry:
    def __init__(self, file_path: str) -> None:
        self.file_path = file_path
        self.language = "python"
        self.size_bytes = 12


class FakeCloner:
    def clone_and_discover(
        self,
        repo: str,
        *,
        branch: str | None = None,
        shallow: bool = True,
    ) -> list[FakeManifestEntry]:
        return [FakeManifestEntry("src/app.py"), FakeManifestEntry("README.md")]


class FakeAnswerGenerator:
    def generate(
        self, query: str, *, query_type: str, context: object
    ) -> GenerationResult:
        return GenerationResult(
            answer="`login` is defined in the route [src/app.py:1-2].",
            citations=[
                Citation(
                    file_path="src/app.py",
                    start_line=1,
                    end_line=2,
                    marker="[src/app.py:1-2]",
                    valid=True,
                    reason="valid",
                )
            ],
            citation_coverage=1.0,
            prompt=BuiltPrompt(
                text="prompt",
                query_type="simple-lookup",
                token_count=1,
                truncated=False,
            ),
            raw_answer="`login` is defined in the route [src/app.py:1-2].",
        )


def test_health_endpoint_shows_component_status() -> None:
    response = asyncio.run(health_check())

    assert response.status == "ok"
    assert response.components["api"].status == "ok"
    assert "database" in response.components


def test_openapi_docs_are_available() -> None:
    app = create_app()
    schema = app.openapi()

    assert app.docs_url == "/docs"
    assert "/auth/google" in schema["paths"]
    assert "/auth/google/callback" in schema["paths"]
    assert "/auth/refresh" in schema["paths"]
    assert "/auth/me" in schema["paths"]
    assert "/api/v1/health" in schema["paths"]
    assert "/api/v1/repos/ingest" in schema["paths"]
    assert "/api/v1/query" in schema["paths"]


def test_ingest_endpoint_triggers_background_ingestion(monkeypatch) -> None:
    REPOSITORIES.clear()
    monkeypatch.setattr(repos, "RepoCloner", FakeCloner)
    background_tasks = BackgroundTasks()
    request = RepositoryIngestRequest(local_path=".", branch="main")

    response = asyncio.run(ingest_repository(request, background_tasks))
    for task in background_tasks.tasks:
        task.func(*task.args, **task.kwargs)

    assert response.status == "pending"
    assert REPOSITORIES[response.id].status == "completed"
    assert REPOSITORIES[response.id].file_count == 2
    assert response.job_id


def test_list_repositories_returns_known_records(monkeypatch) -> None:
    REPOSITORIES.clear()
    monkeypatch.setattr(repos, "RepoCloner", FakeCloner)
    background_tasks = BackgroundTasks()
    request = RepositoryIngestRequest(local_path=".")
    response = asyncio.run(ingest_repository(request, background_tasks))

    listed = asyncio.run(list_repositories())

    assert [record.id for record in listed.repositories] == [response.id]


def test_ingest_request_uses_pydantic_validation() -> None:
    with pytest.raises(ValidationError):
        RepositoryIngestRequest(
            repo_url="https://github.com/example/repo",
            local_path=".",
        )


def test_query_endpoint_returns_answer_citations_and_metadata() -> None:
    app = create_app()
    app.state.answer_generator = FakeAnswerGenerator()
    request_context = SimpleNamespace(app=app)
    query_request = QueryRequest(
        query="Where is login?",
        query_type="simple-lookup",
        context=[
            {
                "id": "chunk-1",
                "file_path": "src/app.py",
                "start_line": 1,
                "end_line": 2,
                "text": "def login():\n    return ok",
            }
        ],
    )

    response = asyncio.run(query_repository(query_request, request_context))

    assert response.answer.startswith("`login`")
    assert response.citations[0].valid is True
    assert response.metadata.citation_coverage == 1.0
    assert response.metadata.used_generator is True


def test_query_endpoint_has_safe_fallback_without_generator() -> None:
    app = create_app()
    request_context = SimpleNamespace(app=app)
    query_request = QueryRequest(
        query="Explain the repository",
        query_type="exploratory",
    )

    response = asyncio.run(query_repository(query_request, request_context))

    assert response.citations == []
    assert response.metadata.used_generator is False
