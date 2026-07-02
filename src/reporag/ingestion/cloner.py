"""Git repository cloning and source file discovery."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

DEFAULT_LANGUAGE_EXTENSIONS: dict[str, str] = {
    ".c": "c",
    ".cc": "cpp",
    ".cpp": "cpp",
    ".cs": "csharp",
    ".css": "css",
    ".go": "go",
    ".h": "c",
    ".hpp": "cpp",
    ".html": "html",
    ".java": "java",
    ".js": "javascript",
    ".jsx": "javascript",
    ".kt": "kotlin",
    ".md": "markdown",
    ".php": "php",
    ".py": "python",
    ".rb": "ruby",
    ".rs": "rust",
    ".scala": "scala",
    ".sh": "shell",
    ".sql": "sql",
    ".swift": "swift",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".vue": "vue",
    ".yaml": "yaml",
    ".yml": "yaml",
}

DEFAULT_IGNORED_DIRECTORIES = frozenset(
    {
        ".git",
        ".hg",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".tox",
        ".venv",
        "__pycache__",
        "build",
        "dist",
        "node_modules",
        "vendor",
    }
)


class RepoCloneError(RuntimeError):
    """Raised when a repository cannot be cloned or discovered."""


@dataclass(frozen=True)
class FileManifestEntry:
    """Metadata for a discovered source file."""

    file_path: str
    language: str
    size_bytes: int


class RepoCloner:
    """Clone Git repositories and return parseable source file manifests."""

    def __init__(
        self,
        *,
        extensions: Mapping[str, str] | None = None,
        ignored_directories: set[str] | frozenset[str] | None = None,
    ) -> None:
        self.extensions = {
            suffix.lower(): language
            for suffix, language in (extensions or DEFAULT_LANGUAGE_EXTENSIONS).items()
        }
        self.ignored_directories = ignored_directories or DEFAULT_IGNORED_DIRECTORIES

    def clone_and_discover(
        self,
        repo: str | Path,
        *,
        branch: str | None = None,
        shallow: bool = True,
    ) -> list[FileManifestEntry]:
        """Clone a repository into a temp directory and return its file manifest."""

        with tempfile.TemporaryDirectory(prefix="reporag-clone-") as temp_dir:
            clone_path = Path(temp_dir) / "repo"
            try:
                self.clone(repo, clone_path, branch=branch, shallow=shallow)
                return self.discover_files(clone_path)
            except Exception as exc:
                shutil.rmtree(clone_path, ignore_errors=True)
                if isinstance(exc, RepoCloneError):
                    raise
                raise RepoCloneError(str(exc)) from exc

    def clone(
        self,
        repo: str | Path,
        destination: str | Path,
        *,
        branch: str | None = None,
        shallow: bool = True,
    ) -> Path:
        """Clone a Git repository URL or local path into ``destination``."""

        destination_path = Path(destination)
        command = ["git", "clone"]
        if shallow:
            command.extend(["--depth", "1"])
        if branch:
            command.extend(["--branch", branch])
        command.extend([str(repo), str(destination_path)])

        try:
            subprocess.run(
                command,
                check=True,
                capture_output=True,
                text=True,
            )
        except FileNotFoundError as exc:
            raise RepoCloneError("git executable was not found") from exc
        except subprocess.CalledProcessError as exc:
            message = exc.stderr.strip() or exc.stdout.strip() or "git clone failed"
            raise RepoCloneError(message) from exc

        return destination_path

    def discover_files(self, repo_path: str | Path) -> list[FileManifestEntry]:
        """Return supported files below ``repo_path`` sorted by relative path."""

        root_path = Path(repo_path).expanduser().resolve()
        if not root_path.exists():
            raise RepoCloneError(f"Repository path does not exist: {repo_path}")
        if not root_path.is_dir():
            raise RepoCloneError(f"Repository path is not a directory: {repo_path}")

        entries: list[FileManifestEntry] = []

        for root, directories, filenames in os.walk(root_path):
            directories[:] = [
                name
                for name in directories
                if name not in self.ignored_directories and not name.startswith(".")
            ]

            for filename in filenames:
                file_path = Path(root) / filename
                language = self.extensions.get(file_path.suffix.lower())
                if language is None:
                    continue

                entries.append(
                    FileManifestEntry(
                        file_path=file_path.relative_to(root_path).as_posix(),
                        language=language,
                        size_bytes=file_path.stat().st_size,
                    )
                )

        return sorted(entries, key=lambda entry: entry.file_path)
