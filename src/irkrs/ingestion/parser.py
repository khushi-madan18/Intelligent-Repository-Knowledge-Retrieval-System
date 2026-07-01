"""Python source parser."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path


class PythonParseError(Exception):
    """Raised when Python source cannot be parsed."""


@dataclass(frozen=True)
class ParsedPythonFile:
    """Parsed Python source and AST."""

    path: str
    source: str
    tree: ast.Module


class PythonParser:
    """Parse Python files using the standard AST module."""

    def parse_file(
        self, path: str | Path, repo_root: str | Path | None = None
    ) -> ParsedPythonFile:
        file_path = Path(path)
        source = file_path.read_text(encoding="utf-8")
        display_path = (
            file_path.relative_to(Path(repo_root)).as_posix()
            if repo_root is not None
            else file_path.as_posix()
        )
        return self.parse_source(source=source, path=display_path)

    def parse_source(self, source: str, path: str = "<memory>") -> ParsedPythonFile:
        try:
            tree = ast.parse(source, filename=path)
        except SyntaxError as exc:
            raise PythonParseError(f"Failed to parse {path}: {exc}") from exc
        return ParsedPythonFile(path=path, source=source, tree=tree)
