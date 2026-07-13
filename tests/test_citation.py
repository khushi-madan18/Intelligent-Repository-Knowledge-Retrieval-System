"""Tests for generated answer citation extraction and validation."""

from src.reporag.generation.citation import (
    citation_coverage,
    extract_and_validate_citations,
    extract_citations,
    validate_citations,
)
from src.reporag.generation.context_assembler import AssembledContext, ContextChunk


def context() -> AssembledContext:
    chunk = ContextChunk(
        id="auth",
        file_path="src/auth.py",
        start_line=10,
        end_line=18,
        text="def authenticate_user():\n    return token",
    )
    return AssembledContext(
        text="### src/auth.py:10-18\n10: def authenticate_user():\n11:     return token",
        chunks=[chunk],
        token_count=8,
        truncated=False,
    )


def test_extracts_citation_markers() -> None:
    citations = extract_citations(
        "Defined in auth [src/auth.py:10-18] and called by API [src/api.py:2-4]."
    )

    assert [(c.file_path, c.start_line, c.end_line) for c in citations] == [
        ("src/auth.py", 10, 18),
        ("src/api.py", 2, 4),
    ]


def test_validates_citations_against_context_chunks() -> None:
    citations = extract_citations("Defined in auth [src/auth.py:10-18].")

    validated = validate_citations(citations, context())

    assert validated[0].valid is True
    assert validated[0].reason == "valid"


def test_flags_invalid_file_and_line_ranges() -> None:
    citations = extract_citations(
        "Bad file [src/missing.py:1-2], bad line [src/auth.py:10-30]."
    )

    validated = validate_citations(citations, context())

    assert [citation.valid for citation in validated] == [False, False]
    assert "file not found" in validated[0].reason
    assert "lines not found" in validated[1].reason


def test_validates_against_context_headers_when_chunks_missing() -> None:
    assembled = AssembledContext(
        text="### src/routes.py:3-5\n3: def login():\n4:     return ok",
        chunks=[],
        token_count=6,
        truncated=False,
    )

    citations = extract_and_validate_citations(
        "Route lives here [src/routes.py:3-4].", assembled
    )

    assert citations[0].valid is True


def test_citation_coverage_reports_valid_ratio() -> None:
    citations = validate_citations(
        extract_citations(
            "One valid [src/auth.py:10-11], one invalid [src/auth.py:30-31]."
        ),
        context(),
    )

    assert citation_coverage(citations) == 0.5
