import asyncio
import os
from unittest.mock import patch

from sqlalchemy.ext.asyncio import AsyncSession

from src.reporag.db.models import Base, IngestionJob, QueryLog, Repository, User
from src.reporag.db.session import get_db


def test_models_are_registered() -> None:
    assert Repository.__tablename__ in Base.metadata.tables
    assert IngestionJob.__tablename__ in Base.metadata.tables
    assert User.__tablename__ in Base.metadata.tables
    assert QueryLog.__tablename__ in Base.metadata.tables


def test_database_url_defaults_to_sqlite() -> None:
    with patch.dict(os.environ, {}, clear=True):
        import src.reporag.config as config_module
        import src.reporag.db.session as session_module

        config_module.get_settings.cache_clear()
        session_module.settings = config_module.get_settings()
        assert session_module.get_database_url().startswith("sqlite+aiosqlite:///")
        config_module.get_settings.cache_clear()


def test_database_url_switches_to_postgres_without_code_changes() -> None:
    postgres_url = "postgresql+asyncpg://reporag:reporag@localhost:5432/reporag"
    with patch.dict(os.environ, {"DATABASE_URL": postgres_url}):
        import src.reporag.config as config_module
        import src.reporag.db.session as session_module

        config_module.get_settings.cache_clear()
        session_module.settings = config_module.get_settings()
        assert session_module.get_database_url() == postgres_url
        config_module.get_settings.cache_clear()


def test_get_db_yields_async_session() -> None:
    async def collect_session() -> AsyncSession:
        async for session in get_db():
            return session
        raise AssertionError("get_db did not yield a session")

    session = asyncio.run(collect_session())

    assert isinstance(session, AsyncSession)
