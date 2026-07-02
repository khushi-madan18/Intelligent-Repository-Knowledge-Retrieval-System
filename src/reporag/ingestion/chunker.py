"""Semantic code chunking that respects extracted symbol boundaries."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable

from reporag.ingestion.symbol_extractor import Symbol

TokenCounter = Callable[[str], int]


@dataclass(frozen=True)
class CodeChunk:
    """A source-code chunk ready for indexing."""

    content: str
    file_path: str
    start_line: int
    end_line: int
    parent_symbol: str | None
    language: str
    token_count: int


class CodeChunker:
    """Create bounded chunks without splitting code symbols unnecessarily."""

    def __init__(
        self,
        max_tokens: int = 512,
        *,
        token_counter: TokenCounter | None = None,
    ) -> None:
        if max_tokens < 1:
            raise ValueError("max_tokens must be at least 1")
        self.max_tokens = max_tokens
        self.soft_limit = max(1, int(max_tokens * 1.1))
        self._count_tokens = token_counter or self._default_token_count

    def chunk(
        self,
        symbols: list[Symbol],
        source: str,
        *,
        file_path: str,
        language: str,
    ) -> list[CodeChunk]:
        """Chunk source using extracted symbol boundaries."""

        chunks: list[CodeChunk] = []
        import_symbols = [symbol for symbol in symbols if symbol.type == "import"]
        semantic_symbols = [symbol for symbol in symbols if symbol.type != "import"]

        if import_symbols:
            chunks.extend(
                self._chunk_imports(import_symbols, source, file_path, language)
            )

        for symbol in semantic_symbols:
            chunks.extend(self._chunk_symbol(symbol, source, file_path, language))

        return chunks

    def _chunk_imports(
        self,
        symbols: list[Symbol],
        source: str,
        file_path: str,
        language: str,
    ) -> list[CodeChunk]:
        sorted_symbols = sorted(symbols, key=lambda symbol: symbol.start_line)
        groups: list[list[Symbol]] = []
        current_group: list[Symbol] = []

        for symbol in sorted_symbols:
            if current_group and symbol.start_line > current_group[-1].end_line + 1:
                groups.append(current_group)
                current_group = []
            current_group.append(symbol)

        if current_group:
            groups.append(current_group)

        return [
            self._build_chunk(
                content=self._source_slice(
                    source,
                    group[0].start_line,
                    group[-1].end_line,
                ),
                file_path=file_path,
                start_line=group[0].start_line,
                end_line=group[-1].end_line,
                parent_symbol="module imports",
                language=language,
            )
            for group in groups
        ]

    def _chunk_symbol(
        self,
        symbol: Symbol,
        source: str,
        file_path: str,
        language: str,
    ) -> list[CodeChunk]:
        content = self._source_slice(source, symbol.start_line, symbol.end_line)
        if self._count_tokens(content) <= self.soft_limit:
            return [
                self._build_chunk(
                    content=content,
                    file_path=file_path,
                    start_line=symbol.start_line,
                    end_line=symbol.end_line,
                    parent_symbol=symbol.name,
                    language=language,
                )
            ]

        if symbol.type == "class" and symbol.children:
            return self._split_class(symbol, source, file_path, language)

        if symbol.type in {"function", "method"}:
            return self._split_large_symbol(symbol, source, file_path, language)

        return self._split_large_symbol(symbol, source, file_path, language)

    def _split_class(
        self,
        symbol: Symbol,
        source: str,
        file_path: str,
        language: str,
    ) -> list[CodeChunk]:
        chunks: list[CodeChunk] = []
        first_child_line = min(child.start_line for child in symbol.children)
        header_end_line = first_child_line - 1
        header_content = self._source_slice(
            source,
            symbol.start_line,
            header_end_line,
        ).rstrip()

        if header_content:
            chunks.append(
                self._build_chunk(
                    content=header_content,
                    file_path=file_path,
                    start_line=symbol.start_line,
                    end_line=header_end_line,
                    parent_symbol=symbol.name,
                    language=language,
                )
            )

        for child in symbol.children:
            chunks.extend(self._chunk_symbol(child, source, file_path, language))

        return chunks

    def _split_large_symbol(
        self,
        symbol: Symbol,
        source: str,
        file_path: str,
        language: str,
    ) -> list[CodeChunk]:
        lines = source.splitlines()
        symbol_lines = lines[symbol.start_line - 1 : symbol.end_line]
        if not symbol_lines:
            return []

        signature = symbol.signature or symbol_lines[0].strip()
        body_start_line = symbol.start_line + 1
        body_lines = symbol_lines[1:]
        body_groups = self._logical_line_groups(body_lines, body_start_line)

        chunks: list[CodeChunk] = []
        current_lines: list[str] = []
        current_start = body_start_line
        current_end = body_start_line - 1

        for group_start, group_end, group_lines in body_groups:
            candidate_lines = current_lines + group_lines
            candidate_content = self._with_signature(signature, candidate_lines)

            if (
                current_lines
                and self._count_tokens(candidate_content) > self.soft_limit
            ):
                chunks.append(
                    self._build_chunk(
                        content=self._with_signature(signature, current_lines),
                        file_path=file_path,
                        start_line=current_start,
                        end_line=current_end,
                        parent_symbol=symbol.name,
                        language=language,
                    )
                )
                current_lines = group_lines
                current_start = group_start
                current_end = group_end
                continue

            if not current_lines:
                current_start = group_start
            current_lines = candidate_lines
            current_end = group_end

        if current_lines:
            chunks.append(
                self._build_chunk(
                    content=self._with_signature(signature, current_lines),
                    file_path=file_path,
                    start_line=current_start,
                    end_line=current_end,
                    parent_symbol=symbol.name,
                    language=language,
                )
            )

        return chunks or [
            self._build_chunk(
                content=signature,
                file_path=file_path,
                start_line=symbol.start_line,
                end_line=symbol.start_line,
                parent_symbol=symbol.name,
                language=language,
            )
        ]

    def _logical_line_groups(
        self,
        lines: list[str],
        start_line: int,
    ) -> list[tuple[int, int, list[str]]]:
        groups: list[tuple[int, int, list[str]]] = []
        current_lines: list[str] = []
        current_start = start_line

        for offset, line in enumerate(lines):
            line_number = start_line + offset
            if not line.strip() and current_lines:
                groups.append(
                    (
                        current_start,
                        line_number - 1,
                        current_lines,
                    )
                )
                current_lines = []
                current_start = line_number + 1
                continue
            if not current_lines:
                current_start = line_number
            current_lines.append(line)

        if current_lines:
            groups.append(
                (
                    current_start,
                    start_line + len(lines) - 1,
                    current_lines,
                )
            )

        return self._split_oversized_groups(groups)

    def _split_oversized_groups(
        self,
        groups: list[tuple[int, int, list[str]]],
    ) -> list[tuple[int, int, list[str]]]:
        split_groups: list[tuple[int, int, list[str]]] = []

        for start_line, end_line, lines in groups:
            if self._count_tokens("\n".join(lines)) <= self.soft_limit:
                split_groups.append((start_line, end_line, lines))
                continue

            for offset, line in enumerate(lines):
                line_number = start_line + offset
                split_groups.append((line_number, line_number, [line]))

        return split_groups

    def _build_chunk(
        self,
        *,
        content: str,
        file_path: str,
        start_line: int,
        end_line: int,
        parent_symbol: str | None,
        language: str,
    ) -> CodeChunk:
        return CodeChunk(
            content=content,
            file_path=file_path,
            start_line=start_line,
            end_line=end_line,
            parent_symbol=parent_symbol,
            language=language,
            token_count=self._count_tokens(content),
        )

    def _source_slice(self, source: str, start_line: int, end_line: int) -> str:
        lines = source.splitlines()
        return "\n".join(lines[start_line - 1 : end_line])

    def _with_signature(self, signature: str, lines: list[str]) -> str:
        body = "\n".join(lines).rstrip()
        return f"{signature}:\n{body}" if body else f"{signature}:"

    def _default_token_count(self, text: str) -> int:
        return len(re.findall(r"\w+|[^\w\s]", text))
