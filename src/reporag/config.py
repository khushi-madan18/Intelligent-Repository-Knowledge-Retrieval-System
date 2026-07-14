"""Centralized application settings loaded from environment and .env files."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, ValidationError, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PLACEHOLDER_SECRETS = {"", "change-me", "changeme", "placeholder", "secret"}


class Settings(BaseSettings):
    """Application settings grouped by subsystem."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # App
    app_env: Literal["development", "test", "staging", "production"] = "development"
    app_name: str = "Intelligent Repository Knowledge Retrieval System"
    api_v1_prefix: str = "/api/v1"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    api_rate_limit_per_minute: int = Field(default=60, ge=1)

    # Repository ingestion
    max_repo_size_mb: int = Field(default=100, ge=1)

    # Database
    database_url: str = "sqlite+aiosqlite:///./data/reporag.db"
    postgres_database_url: str = (
        "postgresql+asyncpg://reporag:reporag@postgres:5432/reporag"
    )

    # Neo4j
    neo4j_uri: str = "bolt://neo4j:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: SecretStr = SecretStr("change-me")

    # Qdrant
    qdrant_url: str = "http://qdrant:6333"
    qdrant_api_key: SecretStr | None = None
    qdrant_collection: str = "code_chunks"

    # LLM
    llm_provider: Literal["openai", "anthropic"] = "openai"
    llm_model: str = "gpt-4o-mini"
    openai_api_key: SecretStr = SecretStr("change-me")
    anthropic_api_key: SecretStr | None = None

    # Auth
    jwt_secret_key: SecretStr = SecretStr("change-me")
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = Field(default=30, ge=1)
    refresh_token_expire_days: int = Field(default=7, ge=1)
    google_client_id: str | None = None
    google_client_secret: SecretStr | None = None

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: str) -> str:
        """Ensure database URLs use async drivers expected by the app."""

        allowed_prefixes = ("sqlite+aiosqlite://", "postgresql+asyncpg://")
        if not value.startswith(allowed_prefixes):
            msg = "DATABASE_URL must use sqlite+aiosqlite or postgresql+asyncpg"
            raise ValueError(msg)
        return value

    @field_validator("api_v1_prefix")
    @classmethod
    def validate_api_prefix(cls, value: str) -> str:
        """Ensure API prefixes are absolute URL paths."""

        if not value.startswith("/"):
            raise ValueError("API_V1_PREFIX must start with /")
        return value.rstrip("/") or "/"

    @model_validator(mode="after")
    def validate_required_production_secrets(self) -> Settings:
        """Require real secret values in production."""

        if self.app_env != "production":
            return self

        missing = []
        for field_name in ("neo4j_password", "openai_api_key", "jwt_secret_key"):
            value = getattr(self, field_name).get_secret_value()
            if value.lower() in PLACEHOLDER_SECRETS:
                missing.append(field_name.upper())

        if self.llm_provider == "anthropic":
            value = (
                self.anthropic_api_key.get_secret_value()
                if self.anthropic_api_key is not None
                else ""
            )
            if value.lower() in PLACEHOLDER_SECRETS:
                missing.append("ANTHROPIC_API_KEY")

        if missing:
            raise ValueError(
                "Production requires non-placeholder secrets for: "
                + ", ".join(sorted(missing))
            )

        return self


@lru_cache
def get_settings() -> Settings:
    """Return cached settings and surface validation errors at startup/import."""

    try:
        return Settings()
    except ValidationError:
        raise


settings = get_settings()
