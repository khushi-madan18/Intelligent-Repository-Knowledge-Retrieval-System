"""AST-aware Python code chunking."""

from __future__ import annotations

import ast
from dataclasses import dataclass

from irkrs.ingestion.parser import ParsedPythonFile


@dataclass(frozen=True)
class CodeChunk:
    """A contiguous source-code chunk."""

    path: str
    kind: str
    name: str
    start_line: int
    end_line: int
    content: str


class PythonChunker:
    """Create chunks without splitting functions or classes mid-body."""

    def chunk(self, parsed_file: ParsedPythonFile) -> list[CodeChunk]:
        lines = parsed_file.source.splitlines()
        chunks: list[CodeChunk] = []
        top_level_nodes = [
            node
            for node in parsed_file.tree.body
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
        ]

        for node in top_level_nodes:
            start_line = node.lineno
            end_line = getattr(node, "end_lineno", node.lineno)
            chunks.append(
                CodeChunk(
                    path=parsed_file.path,
                    kind=self._kind(node),
                    name=node.name,
                    start_line=start_line,
                    end_line=end_line,
                    content="\n".join(lines[start_line - 1 : end_line]),
                )
            )

        if not chunks and parsed_file.source.strip():
            chunks.append(
                CodeChunk(
                    path=parsed_file.path,
                    kind="module",
                    name=parsed_file.path,
                    start_line=1,
                    end_line=len(lines),
                    content=parsed_file.source,
                )
            )

        return chunks

    def _kind(self, node: ast.AST) -> str:
        if isinstance(node, ast.ClassDef):
            return "class"
        if isinstance(node, ast.AsyncFunctionDef):
            return "async_function"
        return "function"
