"""Tree-sitter AST parsing for repository source files."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Callable

import tree_sitter_python
from tree_sitter import Language, Node, Parser


class ASTParserError(ValueError):
    """Raised when an unsupported language or unreadable source is requested."""


@dataclass(frozen=True)
class ASTNodeData:
    """Structured representation of a tree-sitter node."""

    type: str
    text: str
    start_line: int
    end_line: int
    start_column: int
    end_column: int
    has_error: bool
    children: list[ASTNodeData]


@dataclass(frozen=True)
class ParsedAST:
    """Parsed source tree and structured root node."""

    language: str
    source: str
    root_node: ASTNodeData
    has_errors: bool


LanguageFactory = Callable[[], Language]


def _python_language() -> Language:
    return Language(tree_sitter_python.language())


LANGUAGE_FACTORIES: dict[str, LanguageFactory] = {
    "py": _python_language,
    "python": _python_language,
}


class ASTParser:
    """Language-agnostic Tree-sitter parser wrapper."""

    def __init__(
        self,
        *,
        languages: dict[str, LanguageFactory] | None = None,
    ) -> None:
        self.languages = {
            language.lower(): factory
            for language, factory in (languages or LANGUAGE_FACTORIES).items()
        }

    def parse(
        self,
        source: str | bytes,
        *,
        language: str,
    ) -> ParsedAST:
        """Parse source text and return a structured partial AST."""

        normalized_language = language.lower()
        parser = Parser()
        parser.language = self._get_language(normalized_language)

        source_bytes = source if isinstance(source, bytes) else source.encode("utf-8")
        source_text = (
            source.decode("utf-8", errors="replace")
            if isinstance(source, bytes)
            else source
        )
        tree = parser.parse(source_bytes)
        root_node = self._build_node_data(tree.root_node, source_bytes)

        return ParsedAST(
            language=normalized_language,
            source=source_text,
            root_node=root_node,
            has_errors=tree.root_node.has_error,
        )

    def parse_file(
        self,
        path: str | Path,
        *,
        language: str | None = None,
    ) -> ParsedAST:
        """Read and parse a source file."""

        file_path = Path(path)
        source = file_path.read_text(encoding="utf-8")
        return self.parse(
            source, language=language or self._language_from_path(file_path)
        )

    @lru_cache(maxsize=16)
    def _get_language(self, language: str) -> Language:
        try:
            return self.languages[language]()
        except KeyError as exc:
            supported = ", ".join(sorted(self.languages))
            raise ASTParserError(
                f"Unsupported language '{language}'. Supported: {supported}"
            ) from exc

    def _language_from_path(self, path: Path) -> str:
        extension = path.suffix.lower().lstrip(".")
        if extension in self.languages:
            return extension
        raise ASTParserError(f"Could not infer supported language from path: {path}")

    def _build_node_data(self, node: Node, source: bytes) -> ASTNodeData:
        return ASTNodeData(
            type=node.type,
            text=source[node.start_byte : node.end_byte].decode(
                "utf-8",
                errors="replace",
            ),
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            start_column=node.start_point[1],
            end_column=node.end_point[1],
            has_error=node.has_error,
            children=[self._build_node_data(child, source) for child in node.children],
        )
