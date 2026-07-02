from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

import pytest

from reporag.ingestion.cloner import FileManifestEntry, RepoCloneError, RepoCloner


def run_git(repo_path: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=repo_path,
        check=True,
        capture_output=True,
        text=True,
    )


def write_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


@pytest.fixture
def local_git_repo(tmp_path: Path) -> Path:
    repo_path = tmp_path / "source-repo"
    repo_path.mkdir()

    run_git(repo_path, "init", "--initial-branch", "main")
    run_git(repo_path, "config", "user.email", "test@example.com")
    run_git(repo_path, "config", "user.name", "Test User")

    write_file(repo_path / "src" / "app.py", "print('main')\n")
    write_file(repo_path / "src" / "app.ts", "export const app = true;\n")
    write_file(repo_path / "README.txt", "not parseable\n")
    write_file(repo_path / "node_modules" / "ignored.js", "ignored\n")
    run_git(repo_path, "add", ".")
    run_git(repo_path, "commit", "-m", "main files")

    run_git(repo_path, "checkout", "-b", "feature")
    write_file(repo_path / "src" / "feature.go", "package main\n")
    run_git(repo_path, "add", ".")
    run_git(repo_path, "commit", "-m", "feature files")
    run_git(repo_path, "checkout", "main")

    return repo_path


def test_discover_files_filters_supported_extensions(tmp_path: Path) -> None:
    repo_path = tmp_path / "repo"
    write_file(repo_path / "pkg" / "main.py", "print('ok')\n")
    write_file(repo_path / "pkg" / "main.js", "console.log('ok');\n")
    write_file(repo_path / "pkg" / "notes.txt", "ignore\n")
    write_file(repo_path / ".hidden" / "hidden.py", "ignore\n")

    manifest = RepoCloner().discover_files(repo_path)

    assert manifest == [
        FileManifestEntry(
            file_path="pkg/main.js",
            language="javascript",
            size_bytes=19,
        ),
        FileManifestEntry(
            file_path="pkg/main.py",
            language="python",
            size_bytes=12,
        ),
    ]


def test_discover_files_uses_configurable_extensions(tmp_path: Path) -> None:
    repo_path = tmp_path / "repo"
    write_file(repo_path / "docs" / "guide.txt", "hello\n")
    write_file(repo_path / "src" / "app.py", "print('ok')\n")

    manifest = RepoCloner(extensions={".txt": "text"}).discover_files(repo_path)

    assert manifest == [
        FileManifestEntry(
            file_path="docs/guide.txt",
            language="text",
            size_bytes=6,
        )
    ]


def test_clone_and_discover_supports_branch_selection(
    local_git_repo: Path,
) -> None:
    manifest = RepoCloner().clone_and_discover(
        local_git_repo,
        branch="feature",
        shallow=True,
    )

    paths = [entry.file_path for entry in manifest]
    assert "src/app.py" in paths
    assert "src/app.ts" in paths
    assert "src/feature.go" in paths
    assert "README.txt" not in paths


def test_clone_builds_https_branch_and_shallow_command(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_commands: list[list[str]] = []

    def fake_run(command: list[str], **kwargs: object) -> object:
        captured_commands.append(command)
        assert kwargs["check"] is True
        assert kwargs["capture_output"] is True
        assert kwargs["text"] is True
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr("reporag.ingestion.cloner.subprocess.run", fake_run)

    RepoCloner().clone(
        "https://github.com/pallets/click",
        tmp_path / "clone",
        branch="main",
        shallow=True,
    )

    assert captured_commands == [
        [
            "git",
            "clone",
            "--depth",
            "1",
            "--branch",
            "main",
            "https://github.com/pallets/click",
            str(tmp_path / "clone"),
        ]
    ]


def test_clone_and_discover_cleans_up_after_error(
    local_git_repo: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    temp_root = tmp_path / "temp-root"
    created_temp_dirs: list[Path] = []
    original_temporary_directory = tempfile.TemporaryDirectory

    def tracked_temporary_directory(*args: object, **kwargs: object) -> object:
        kwargs["dir"] = temp_root
        temp_dir = original_temporary_directory(*args, **kwargs)
        created_temp_dirs.append(Path(temp_dir.name))
        return temp_dir

    temp_root.mkdir()
    monkeypatch.setattr(
        "reporag.ingestion.cloner.tempfile.TemporaryDirectory",
        tracked_temporary_directory,
    )

    with pytest.raises(RepoCloneError):
        RepoCloner().clone_and_discover(local_git_repo, branch="missing-branch")

    assert created_temp_dirs
    assert all(not path.exists() for path in created_temp_dirs)
