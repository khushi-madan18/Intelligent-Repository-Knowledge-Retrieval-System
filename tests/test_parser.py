from __future__ import annotations

from pathlib import Path

import pytest

from reporag.ingestion.parser import ASTParser, ASTParserError


def find_first_node_type(node: object, node_type: str) -> object | None:
    if getattr(node, "type") == node_type:
        return node
    for child in getattr(node, "children"):
        found = find_first_node_type(child, node_type)
        if found is not None:
            return found
    return None


def test_parse_valid_python_source_returns_structured_ast() -> None:
    source = "def hello():\n    return 42\n"

    parsed = ASTParser().parse(source, language="python")

    assert parsed.language == "python"
    assert parsed.source == source
    assert parsed.has_errors is False
    assert parsed.root_node.type == "module"

    function_node = find_first_node_type(parsed.root_node, "function_definition")
    assert function_node is not None
    assert getattr(function_node, "text") == source.strip()
    assert getattr(function_node, "start_line") == 1
    assert getattr(function_node, "end_line") == 2

    return_node = find_first_node_type(parsed.root_node, "return_statement")
    assert return_node is not None
    assert getattr(return_node, "text") == "return 42"
    assert getattr(return_node, "start_line") == 2
    assert getattr(return_node, "end_line") == 2


def test_parse_syntax_error_returns_partial_ast() -> None:
    parsed = ASTParser().parse("def broken(:\n    return 42\n", language="python")

    assert parsed.root_node.type == "module"
    assert parsed.has_errors is True
    assert parsed.root_node.has_error is True
    assert parsed.root_node.children


def test_parse_file_infers_language_from_extension(tmp_path: Path) -> None:
    source_path = tmp_path / "example.py"
    source_path.write_text("value = 42\n", encoding="utf-8")

    parsed = ASTParser().parse_file(source_path)

    assert parsed.language == "py"
    assert parsed.root_node.type == "module"
    assert find_first_node_type(parsed.root_node, "assignment") is not None


def test_parser_rejects_unsupported_language() -> None:
    with pytest.raises(ASTParserError, match="Unsupported language"):
        ASTParser().parse("let value = 42;", language="javascript")
