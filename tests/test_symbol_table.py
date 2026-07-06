from __future__ import annotations

from reporag.graph.symbol_table import SymbolTable, SymbolTableBuilder, SymbolTableInput
from reporag.ingestion.parser import ASTParser
from reporag.ingestion.symbol_extractor import SymbolExtractor


def analyze(file_path: str, source: str) -> SymbolTableInput:
    parsed = ASTParser().parse(source, language="python")
    symbols = SymbolExtractor().extract(parsed, file_path)
    return SymbolTableInput(file_path=file_path, symbols=symbols)


def test_registers_symbols_with_fully_qualified_names() -> None:
    file_input = analyze(
        "app/service.py",
        '''def load():
    """Load docs."""
    return 1

class UserService:
    @staticmethod
    def build(name: str):
        return name
''',
    )

    table = SymbolTableBuilder().build([file_input])

    qualified_names = [record.qualified_name for record in table.records]
    assert qualified_names == [
        "app.service.UserService",
        "app.service.UserService.build",
        "app.service.load",
    ]

    load_record = table.lookup_qualified("app.service.load")[0]
    assert load_record.name == "load"
    assert load_record.type == "function"
    assert load_record.file_path == "app/service.py"
    assert load_record.start_line == 1
    assert load_record.end_line == 3
    assert load_record.signature == "def load()"
    assert load_record.docstring == "Load docs."

    method_record = table.lookup_exact("build")[0]
    assert method_record.qualified_name == "app.service.UserService.build"
    assert method_record.parent_symbol == "app.service.UserService"


def test_exact_lookup_handles_name_collisions_across_files() -> None:
    table = SymbolTableBuilder().build(
        [
            analyze("app/a.py", "def load():\n    return 'a'\n"),
            analyze("app/b.py", "def load():\n    return 'b'\n"),
        ]
    )

    records = table.lookup_exact("load")

    assert [record.qualified_name for record in records] == [
        "app.a.load",
        "app.b.load",
    ]
    assert records[0].symbol_id != records[1].symbol_id


def test_lookup_by_regex_and_file_path() -> None:
    table = SymbolTableBuilder().build(
        [
            analyze(
                "app/users.py",
                """class UserService:
    def create_user(self):
        return None
""",
            ),
            analyze("app/orders.py", "def create_order():\n    return None\n"),
        ]
    )

    regex_records = table.lookup_regex(r"create_.*")
    file_records = table.lookup_file("app/users.py")

    assert [record.qualified_name for record in regex_records] == [
        "app.orders.create_order",
        "app.users.UserService.create_user",
    ]
    assert [record.qualified_name for record in file_records] == [
        "app.users.UserService",
        "app.users.UserService.create_user",
    ]


def test_json_serialization_round_trip() -> None:
    table = SymbolTableBuilder().build(
        [
            analyze("app/a.py", "def load():\n    return 'a'\n"),
            analyze("app/b.py", "class Loader:\n    pass\n"),
        ]
    )

    restored = SymbolTable.from_json(table.to_json())

    assert restored.records == table.records
    assert restored.lookup_qualified("app.a.load") == table.lookup_qualified(
        "app.a.load"
    )
