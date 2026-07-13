"""Repository ingestion API routes."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, BackgroundTasks
from pydantic import BaseModel, Field, HttpUrl, model_validator

from src.reporag.ingestion.cloner import RepoCloner, RepoCloneError

router = APIRouter(prefix="/repos", tags=["repositories"])

RepoStatus = Literal["pending", "running", "completed", "failed"]


@dataclass
class RepositoryRecord:
    """In-memory repository ingestion state."""

    id: str
    source: str
    branch: str
    status: RepoStatus
    job_id: str
    shallow: bool = True
    file_count: int = 0
    error: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


REPOSITORIES: dict[str, RepositoryRecord] = {}


class RepositoryIngestRequest(BaseModel):
    """Request to ingest a repository."""

    repo_url: HttpUrl | None = Field(
        default=None, description="Public Git repository URL"
    )
    local_path: str | None = Field(default=None, description="Local repository path")
    branch: str = Field(default="main", min_length=1)
    shallow: bool = True

    @property
    def source(self) -> str:
        """Return the selected source as a string."""

        if self.repo_url is not None:
            return str(self.repo_url)
        return self.local_path or ""

    @model_validator(mode="after")
    def validate_source(self) -> RepositoryIngestRequest:
        """Require exactly one repository source."""

        if bool(self.repo_url) == bool(self.local_path):
            raise ValueError("Provide exactly one of repo_url or local_path")
        return self


class RepositoryResponse(BaseModel):
    """Repository ingestion response."""

    id: str
    source: str
    branch: str
    status: RepoStatus
    job_id: str
    shallow: bool
    file_count: int
    error: str | None = None
    created_at: datetime
    updated_at: datetime


class RepositoryListResponse(BaseModel):
    """Repository list response."""

    repositories: list[RepositoryResponse]


@router.post("/ingest", response_model=RepositoryResponse, status_code=202)
async def ingest_repository(
    request: RepositoryIngestRequest,
    background_tasks: BackgroundTasks,
) -> RepositoryResponse:
    """Trigger repository ingestion in the background."""

    record = RepositoryRecord(
        id=str(uuid.uuid4()),
        source=request.source,
        branch=request.branch,
        status="pending",
        job_id=str(uuid.uuid4()),
        shallow=request.shallow,
    )
    REPOSITORIES[record.id] = record
    background_tasks.add_task(_run_ingestion, record.id)
    return _to_response(record)


@router.get("", response_model=RepositoryListResponse)
async def list_repositories() -> RepositoryListResponse:
    """Return repositories known to this API process."""

    ordered = sorted(REPOSITORIES.values(), key=lambda record: record.created_at)
    return RepositoryListResponse(
        repositories=[_to_response(record) for record in ordered]
    )


def _run_ingestion(repository_id: str) -> None:
    record = REPOSITORIES[repository_id]
    record.status = "running"
    record.updated_at = datetime.now(UTC)
    try:
        manifest = RepoCloner().clone_and_discover(
            record.source,
            branch=record.branch,
            shallow=record.shallow,
        )
    except RepoCloneError as exc:
        record.status = "failed"
        record.error = str(exc)
        record.updated_at = datetime.now(UTC)
        return

    record.status = "completed"
    record.file_count = len(manifest)
    record.updated_at = datetime.now(UTC)


def _to_response(record: RepositoryRecord) -> RepositoryResponse:
    return RepositoryResponse(
        id=record.id,
        source=record.source,
        branch=record.branch,
        status=record.status,
        job_id=record.job_id,
        shallow=record.shallow,
        file_count=record.file_count,
        error=record.error,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )
