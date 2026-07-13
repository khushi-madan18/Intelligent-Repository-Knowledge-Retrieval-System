"""Citation extraction and validation for generated answers."""

from __future__ import annotations

import re
from dataclasses import dataclass

from src.reporag.generation.context_assembler import AssembledContext

CITATION_PATTERN = re.compile(r"\[([^\[\]]+?):(\d+)-(\d+)\]")
CONTEXT_HEADER_PATTERN = re.compile(r"^###\s+(.+?):(\d+)-(\d+)\s*$")


@dataclass(frozen=True)
class Citation:
    """Line-level source citation extracted from an answer."""

    file_path: str
    start_line: int
    end_line: int
    marker: str
    valid: bool = False
    reason: str = ""


def extract_citations(answer: str) -> list[Citation]:
    """Extract citation markers in [file_path:start_line-end_line] format."""

    citations: list[Citation] = []
    for match in CITATION_PATTERN.finditer(answer):
        start_line = int(match.group(2))
        end_line = int(match.group(3))
        citations.append(
            Citation(
                file_path=match.group(1),
                start_line=start_line,
                end_line=end_line,
                marker=match.group(0),
                valid=start_line <= end_line,
                reason="" if start_line <= end_line else "start_line exceeds end_line",
            )
        )
    return citations


def validate_citations(
    citations: list[Citation], context: AssembledContext
) -> list[Citation]:
    """Validate citations against retrieved context line ranges."""

    available_lines = _available_context_lines(context)
    validated: list[Citation] = []
    for citation in citations:
        if citation.start_line > citation.end_line:
            validated.append(
                Citation(
                    file_path=citation.file_path,
                    start_line=citation.start_line,
                    end_line=citation.end_line,
                    marker=citation.marker,
                    valid=False,
                    reason="start_line exceeds end_line",
                )
            )
            continue

        file_lines = available_lines.get(citation.file_path)
        if not file_lines:
            validated.append(
                Citation(
                    file_path=citation.file_path,
                    start_line=citation.start_line,
                    end_line=citation.end_line,
                    marker=citation.marker,
                    valid=False,
                    reason="file not found in retrieved context",
                )
            )
            continue

        cited_lines = set(range(citation.start_line, citation.end_line + 1))
        missing = sorted(cited_lines - file_lines)
        if missing:
            reason = f"lines not found in retrieved context: {missing[0]}"
            validated.append(
                Citation(
                    file_path=citation.file_path,
                    start_line=citation.start_line,
                    end_line=citation.end_line,
                    marker=citation.marker,
                    valid=False,
                    reason=reason,
                )
            )
            continue

        validated.append(
            Citation(
                file_path=citation.file_path,
                start_line=citation.start_line,
                end_line=citation.end_line,
                marker=citation.marker,
                valid=True,
                reason="valid",
            )
        )
    return validated


def citation_coverage(citations: list[Citation]) -> float:
    """Return valid citation ratio from 0 to 1."""

    if not citations:
        return 0.0
    valid_count = sum(1 for citation in citations if citation.valid)
    return valid_count / len(citations)


def extract_and_validate_citations(
    answer: str, context: AssembledContext
) -> list[Citation]:
    """Extract citation markers and validate them against context."""

    return validate_citations(extract_citations(answer), context)


def _available_context_lines(context: AssembledContext) -> dict[str, set[int]]:
    available: dict[str, set[int]] = {}
    for chunk in context.chunks:
        available.setdefault(chunk.file_path, set()).update(
            range(chunk.start_line, chunk.end_line + 1)
        )

    current_file: str | None = None
    for raw_line in context.text.splitlines():
        header = CONTEXT_HEADER_PATTERN.match(raw_line)
        if header:
            current_file = header.group(1)
            start_line = int(header.group(2))
            end_line = int(header.group(3))
            available.setdefault(current_file, set()).update(
                range(start_line, end_line + 1)
            )
            continue

        if current_file is None:
            continue

        line_number, _, _line_text = raw_line.partition(":")
        if line_number.strip().isdigit():
            available.setdefault(current_file, set()).add(int(line_number.strip()))

    return available
