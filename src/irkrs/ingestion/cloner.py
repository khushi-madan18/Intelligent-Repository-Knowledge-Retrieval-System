"""Repository file discovery.

This module starts with local directory discovery. Remote Git cloning can be
added later behind the same interface.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from irkrs.config import settings


class RepositoryDiscoveryError(Exception):
    """Raised when repository discovery cannot continue."""


@dataclass(frozen=True)
class FileEntry:
    """Metadata for a source file discovered in a repository."""

    path: str
    language: str
    size_bytes: int


class RepositoryDiscovery:
    """Find supported source files in a local repository directory."""

    def __init__(self, repo_path: str | Path) -> None:
        self.repo_path = Path(repo_path).expanduser().resolve()
        if not self.repo_path.exists():
            raise RepositoryDiscoveryError(
                f"Repository path does not exist: {repo_path}"
            )
        if not self.repo_path.is_dir():
            raise RepositoryDiscoveryError(
                f"Repository path is not a directory: {repo_path}"
            )

    def discover(self) -> list[FileEntry]:
        """Return supported source files sorted by relative path."""

        entries: list[FileEntry] = []
        total_size = 0
        max_size = settings.max_repo_size_mb * 1024 * 1024

        for root, dirs, files in os.walk(self.repo_path):
            dirs[:] = [
                name
                for name in dirs
                if name not in settings.ignored_directories and not name.startswith(".")
            ]

            for filename in files:
                file_path = Path(root) / filename
                language = settings.supported_extensions.get(file_path.suffix.lower())
                if language is None:
                    continue

                size = file_path.stat().st_size
                total_size += size
                if total_size > max_size:
                    raise RepositoryDiscoveryError(
                        f"Repository exceeds {settings.max_repo_size_mb} MB"
                    )

                entries.append(
                    FileEntry(
                        path=file_path.relative_to(self.repo_path).as_posix(),
                        language=language,
                        size_bytes=size,
                    )
                )

        return sorted(entries, key=lambda entry: entry.path)
