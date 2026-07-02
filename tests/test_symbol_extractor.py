from __future__ import annotations

import pytest

from reporag.ingestion.parser import ASTParser
from reporag.ingestion.symbol_extractor import (
    ImportName,
    SymbolExtractionError,
    SymbolExtractor,
)


def parse_symbols(source: str) -> list[object]:
    parsed = ASTParser().parse(source, language="python")
    return SymbolExtractor().extract(parsed, "app/service.py")


def test_extracts_python_imports_functions_classes_and_methods() -> None:
    source = '''import os, numpy as np
from pathlib import Path as P, PurePath

@router.get("/users")
async def fetch_user(user_id: int) -> dict:
    """Fetch a user."""
    return {}

@dataclass
class UserService(BaseService, Mixin):
    """Service docs."""

    @staticmethod
    def build(name: str):
        """Build docs."""
        return name

    @property
    def label(self):
        return self.name
'''

    symbols = parse_symbols(source)

    assert [symbol.type for symbol in symbols] == [
        "import",
        "import",
        "function",
        "class",
    ]

    import_symbol = symbols[0]
    assert import_symbol.imports == [
        ImportName("os"),
        ImportName("numpy", "np"),
    ]
    assert import_symbol.is_from_import is False

    from_import = symbols[1]
    assert from_import.module == "pathlib"
    assert from_import.imports == [
        ImportName("Path", "P"),
        ImportName("PurePath"),
    ]
    assert from_import.is_from_import is True

    function = symbols[2]
    assert function.name == "fetch_user"
    assert function.signature == "async def fetch_user(user_id: int) -> dict"
    assert function.docstring == "Fetch a user."
    assert function.decorators == ['@router.get("/users")']
    assert function.is_async is True
    assert function.start_line == 5
    assert function.end_line == 7

    service = symbols[3]
    assert service.name == "UserService"
    assert service.signature == "class UserService(BaseService, Mixin)"
    assert service.docstring == "Service docs."
    assert service.decorators == ["@dataclass"]
    assert service.bases == ["BaseService", "Mixin"]
    assert [method.name for method in service.children] == [
        "UserService.build",
        "UserService.label",
    ]

    build_method = service.children[0]
    assert build_method.type == "method"
    assert build_method.signature == "def build(name: str)"
    assert build_method.docstring == "Build docs."
    assert build_method.is_static is True
    assert build_method.is_classmethod is False
    assert build_method.is_property is False

    label_method = service.children[1]
    assert label_method.is_property is True


def test_extracts_symbols_from_partial_ast_with_errors() -> None:
    source = """def valid_before():
    return 1

def broken(:
    return 2

def valid_after():
    return 3
"""
    parsed = ASTParser().parse(source, language="python")

    symbols = SymbolExtractor().extract(parsed, "broken.py")

    assert parsed.has_errors is True
    assert [symbol.name for symbol in symbols] == ["valid_before", "valid_after"]


def test_rejects_unsupported_languages() -> None:
    parsed = ASTParser().parse("value = 42\n", language="python")

    with pytest.raises(SymbolExtractionError, match="not supported"):
        SymbolExtractor().extract(
            parsed.__class__(
                language="javascript",
                source=parsed.source,
                root_node=parsed.root_node,
                has_errors=False,
            ),
            "app.js",
        )
