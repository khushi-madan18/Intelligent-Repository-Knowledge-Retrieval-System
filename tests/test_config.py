import pytest
from pydantic import SecretStr, ValidationError

from src.reporag.config import Settings


def test_settings_defaults_for_development() -> None:
    settings = Settings(_env_file=None)

    assert settings.app_env == "development"
    assert settings.database_url.startswith("sqlite+aiosqlite:///")
    assert isinstance(settings.neo4j_password, SecretStr)
    assert isinstance(settings.openai_api_key, SecretStr)
    assert isinstance(settings.jwt_secret_key, SecretStr)


def test_invalid_database_url_raises_validation_error() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, database_url="sqlite:///./data/reporag.db")


def test_production_placeholder_secrets_raise_validation_error() -> None:
    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None, app_env="production")

    message = str(exc_info.value)
    assert "JWT_SECRET_KEY" in message
    assert "NEO4J_PASSWORD" in message
    assert "OPENAI_API_KEY" in message


def test_production_accepts_real_secrets() -> None:
    settings = Settings(
        _env_file=None,
        app_env="production",
        neo4j_password="neo4j-super-secret",
        openai_api_key="openai-super-secret",
        jwt_secret_key="jwt-super-secret",
    )

    assert settings.app_env == "production"
