"""Async database engine and session factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.reporag.config import settings


def get_database_url() -> str:
    """Return the active database URL.

    SQLite is the default for local development. Setting ``DATABASE_URL`` to a
    Postgres async URL switches the session factory without code changes.
    """

    return settings.database_url


def ensure_sqlite_parent(database_url: str) -> None:
    """Create the SQLite database parent directory when using a file path."""

    if not database_url.startswith("sqlite"):
        return
    if database_url in {"sqlite+aiosqlite:///:memory:", "sqlite:///:memory:"}:
        return

    path = database_url.split("///", 1)[-1]
    Path(path).expanduser().parent.mkdir(parents=True, exist_ok=True)


DATABASE_URL = get_database_url()
ensure_sqlite_parent(DATABASE_URL)

engine = create_async_engine(DATABASE_URL, future=True)
async_session_factory = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
    class_=AsyncSession,
)


async def get_db() -> AsyncIterator[AsyncSession]:
    """Yield an async database session."""

    async with async_session_factory() as session:
        yield session
