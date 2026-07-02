from __future__ import annotations

from reporag.ingestion.chunker import CodeChunker
from reporag.ingestion.parser import ASTParser
from reporag.ingestion.symbol_extractor import Symbol, SymbolExtractor


def parse_symbols(source: str) -> list[Symbol]:
    parsed = ASTParser().parse(source, language="python")
    return SymbolExtractor().extract(parsed, "app/service.py")


def simple_count(text: str) -> int:
    return len(text.split())


def test_chunks_small_symbols_without_splitting_scope_boundaries() -> None:
    source = """import os
from pathlib import Path

def add(left, right):
    return left + right

class Calculator:
    def multiply(self, left, right):
        return left * right
"""
    symbols = parse_symbols(source)

    chunks = CodeChunker(max_tokens=100, token_counter=simple_count).chunk(
        symbols,
        source,
        file_path="app/service.py",
        language="python",
    )

    assert [
        (chunk.parent_symbol, chunk.start_line, chunk.end_line) for chunk in chunks
    ] == [
        ("module imports", 1, 2),
        ("add", 4, 5),
        ("Calculator", 7, 9),
    ]
    assert chunks[0].file_path == "app/service.py"
    assert chunks[0].language == "python"
    assert all(chunk.token_count <= 110 for chunk in chunks)


def test_large_class_splits_at_method_boundaries() -> None:
    source = """class Service:
    \"\"\"Service docs.\"\"\"

    def first(self):
        alpha = 1
        beta = 2
        return alpha + beta

    def second(self):
        gamma = 3
        delta = 4
        return gamma + delta
"""
    symbols = parse_symbols(source)

    chunks = CodeChunker(max_tokens=14, token_counter=simple_count).chunk(
        symbols,
        source,
        file_path="app/service.py",
        language="python",
    )

    assert [chunk.parent_symbol for chunk in chunks] == [
        "Service",
        "Service.first",
        "Service.second",
    ]
    assert chunks[0].content == 'class Service:\n    """Service docs."""'
    assert chunks[1].content.lstrip().startswith("def first(self):")
    assert chunks[1].end_line == 7
    assert chunks[2].content.lstrip().startswith("def second(self):")
    assert chunks[2].start_line == 9


def test_large_function_splits_with_signature_overlap() -> None:
    source = """def process(items):
    first = items[0]
    second = items[1]

    third = items[2]
    fourth = items[3]

    return first + second + third + fourth
"""
    symbols = parse_symbols(source)

    chunks = CodeChunker(max_tokens=9, token_counter=simple_count).chunk(
        symbols,
        source,
        file_path="app/service.py",
        language="python",
    )

    assert len(chunks) == 3
    assert all(chunk.parent_symbol == "process" for chunk in chunks)
    assert all(chunk.content.startswith("def process(items):") for chunk in chunks)
    assert [(chunk.start_line, chunk.end_line) for chunk in chunks] == [
        (2, 3),
        (5, 6),
        (8, 8),
    ]
    assert all(chunk.token_count <= 10 for chunk in chunks)


def test_end_to_end_parse_extract_chunk_pipeline() -> None:
    source = """import os

def hello():
    return os.getcwd()
"""
    parsed = ASTParser().parse(source, language="python")
    symbols = SymbolExtractor().extract(parsed, "hello.py")

    chunks = CodeChunker(max_tokens=64).chunk(
        symbols,
        parsed.source,
        file_path="hello.py",
        language=parsed.language,
    )

    assert [
        (chunk.parent_symbol, chunk.start_line, chunk.end_line) for chunk in chunks
    ] == [
        ("module imports", 1, 1),
        ("hello", 3, 4),
    ]
