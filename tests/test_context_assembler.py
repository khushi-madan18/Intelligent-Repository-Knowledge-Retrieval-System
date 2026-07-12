"""Tests for prompt context assembly."""

from src.reporag.generation.context_assembler import ContextAssembler, estimate_tokens
from src.reporag.retrieval.vector_search import VectorSearchResult


def result(
    result_id: str,
    file_path: str,
    start_line: int,
    end_line: int,
    text: str,
    score: float,
) -> VectorSearchResult:
    return VectorSearchResult(
        id=result_id,
        score=score,
        payload={
            "id": result_id,
            "source_path": file_path,
            "start_line": start_line,
            "end_line": end_line,
            "text": text,
        },
        collection_name="test",
        content_type="code",
        file_path=file_path,
        start_line=start_line,
        end_line=end_line,
        chunk_text=text,
    )


def test_chunks_ordered_by_file_then_line() -> None:
    assembled = ContextAssembler(max_tokens=200).assemble(
        [
            result("b2", "b.py", 20, 21, "b20\nb21", 0.9),
            result("a2", "a.py", 10, 11, "a10\na11", 0.2),
            result("a1", "a.py", 1, 2, "a1\na2", 0.1),
        ]
    )

    assert [(chunk.file_path, chunk.start_line) for chunk in assembled.chunks] == [
        ("a.py", 1),
        ("a.py", 10),
        ("b.py", 20),
    ]


def test_overlapping_chunks_are_merged() -> None:
    assembled = ContextAssembler(max_tokens=200).assemble(
        [
            result(
                "one",
                "auth.py",
                1,
                3,
                "def auth():\n    user = load()\n    return user",
                0.5,
            ),
            result(
                "two",
                "auth.py",
                3,
                5,
                "    return user\n\ndef logout():\n    pass",
                0.9,
            ),
        ]
    )

    assert len(assembled.chunks) == 1
    assert assembled.chunks[0].start_line == 1
    assert assembled.chunks[0].end_line == 5
    assert assembled.chunks[0].text.count("return user") == 1
    assert assembled.chunks[0].score == 0.9


def test_each_chunk_has_file_header_and_line_numbered_code() -> None:
    assembled = ContextAssembler(max_tokens=200).assemble(
        [result("one", "src/auth.py", 7, 8, "def login():\n    return token", 1.0)]
    )

    assert "### src/auth.py:7-8" in assembled.text
    assert "7: def login():" in assembled.text
    assert "8:     return token" in assembled.text


def test_total_tokens_within_max_tokens() -> None:
    assembled = ContextAssembler(max_tokens=12).assemble(
        [
            result("high", "a.py", 1, 2, "one two\nthree four", 1.0),
            result("low", "b.py", 1, 2, "five six\nseven eight", 0.1),
        ]
    )

    assert assembled.token_count <= 12
    assert assembled.truncated is True


def test_highest_ranked_prioritized_when_truncating() -> None:
    assembled = ContextAssembler(max_tokens=8).assemble(
        [
            result("low", "a.py", 1, 1, "low priority chunk", 0.1),
            result("high", "z.py", 1, 1, "high priority chunk", 10.0),
        ]
    )

    assert [chunk.id for chunk in assembled.chunks] == ["high"]
    assert "high priority chunk" in assembled.text
    assert "low priority chunk" not in assembled.text


def test_single_large_chunk_is_truncated_to_budget() -> None:
    assembled = ContextAssembler(max_tokens=10).assemble(
        [
            result(
                "large",
                "large.py",
                10,
                13,
                "alpha beta gamma\ndelta epsilon zeta\neta theta iota\nkappa lambda mu",
                1.0,
            )
        ]
    )

    assert assembled.token_count <= 10
    assert assembled.truncated is True
    assert assembled.chunks[0].start_line == 10


def test_estimate_tokens_uses_whitespace_words() -> None:
    assert estimate_tokens("one two\nthree") == 3
