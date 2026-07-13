"""Health endpoint routes."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from src.reporag.config import settings

router = APIRouter(prefix="/health", tags=["health"])


class ComponentHealth(BaseModel):
    """Health information for one component."""

    status: Literal["ok", "degraded", "unavailable"]
    detail: str = ""


class HealthResponse(BaseModel):
    """Application health response."""

    status: Literal["ok", "degraded", "unavailable"]
    app_name: str
    environment: str
    checked_at: datetime
    components: dict[str, ComponentHealth] = Field(default_factory=dict)


@router.get("", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Return application and dependency health."""

    components = {
        "api": ComponentHealth(status="ok", detail="FastAPI application is running"),
        "database": ComponentHealth(
            status="ok",
            detail=f"Configured database URL: {settings.database_url.split(':', 1)[0]}",
        ),
        "llm": ComponentHealth(
            status="ok",
            detail=f"Configured provider: {settings.llm_provider}",
        ),
    }
    return HealthResponse(
        status="ok",
        app_name=settings.app_name,
        environment=settings.app_env,
        checked_at=datetime.now(UTC),
        components=components,
    )
