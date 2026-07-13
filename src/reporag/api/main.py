"""FastAPI application entrypoint."""

from fastapi import FastAPI

from src.reporag.api.routes import auth, query, repos
from src.reporag.api.routes import health as health_routes
from src.reporag.config import settings


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""

    application = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        docs_url="/docs",
        openapi_url="/openapi.json",
    )
    application.include_router(auth.router)
    application.include_router(health_routes.router, prefix=settings.api_v1_prefix)
    application.include_router(repos.router, prefix=settings.api_v1_prefix)
    application.include_router(query.router, prefix=settings.api_v1_prefix)
    return application


app = create_app()


def health() -> dict[str, str]:
    """Return basic application health for scaffold compatibility."""

    return {"status": "ok"}
