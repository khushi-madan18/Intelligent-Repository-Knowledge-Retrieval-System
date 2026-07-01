"""Application configuration."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Settings:
    """Runtime settings for repository ingestion."""

    max_repo_size_mb: int = 100
    supported_extensions: dict[str, str] = field(
        default_factory=lambda: {
            ".py": "python",
        }
    )
    ignored_directories: frozenset[str] = frozenset(
        {
            ".git",
            ".venv",
            "__pycache__",
            "build",
            "dist",
            "node_modules",
            ".pytest_cache",
        }
    )


settings = Settings()
