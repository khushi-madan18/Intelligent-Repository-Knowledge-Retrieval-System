"""Global symbol table with lookup and JSON serialization."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from reporag.ingestion.symbol_extractor import Symbol


@dataclass(frozen=True)
class SymbolTableInput:
    """Symbols extracted from one source file."""

    file_path: str
    symbols: list[Symbol]


@dataclass(frozen=True)
class SymbolRecord:
    """A globally registered symbol with source metadata."""

    symbol_id: str
    name: str
    qualified_name: str
    type: str
    file_path: str
    module: str
    start_line: int
    end_line: int
    signature: str = ""
    docstring: str = ""
    decorators: list[str] = field(default_factory=list)
    parent_symbol: str | None = None
    is_async: bool = False
    bases: list[str] = field(default_factory=list)


class SymbolTable:
    """Central registry for looking up repository symbols."""

    def __init__(self, records: list[SymbolRecord] | None = None) -> None:
        self._records: dict[str, SymbolRecord] = {}
        self._by_name: dict[str, list[str]] = {}
        self._by_qualified_name: dict[str, list[str]] = {}
        self._by_file_path: dict[str, list[str]] = {}

        for record in records or []:
            self.add(record)

    @property
    def records(self) -> list[SymbolRecord]:
        """Return all records sorted by qualified name and source position."""

        return sorted(
            self._records.values(),
            key=lambda record: (
                record.qualified_name,
                record.file_path,
                record.start_line,
                record.end_line,
            ),
        )

    def add(self, record: SymbolRecord) -> None:
        """Add or replace a symbol record by id."""

        self._records[record.symbol_id] = record
        self._by_name.setdefault(record.name, []).append(record.symbol_id)
        self._by_qualified_name.setdefault(record.qualified_name, []).append(
            record.symbol_id
        )
        self._by_file_path.setdefault(record.file_path, []).append(record.symbol_id)

    def lookup_exact(self, name: str) -> list[SymbolRecord]:
        """Lookup records by exact short name."""

        return self._records_for_ids(self._by_name.get(name, []))

    def lookup_qualified(self, qualified_name: str) -> list[SymbolRecord]:
        """Lookup records by fully qualified name."""

        return self._records_for_ids(self._by_qualified_name.get(qualified_name, []))

    def lookup_regex(self, pattern: str) -> list[SymbolRecord]:
        """Lookup records by regex over short and qualified names."""

        compiled = re.compile(pattern)
        return [
            record
            for record in self.records
            if compiled.search(record.name) or compiled.search(record.qualified_name)
        ]

    def lookup_file(self, file_path: str) -> list[SymbolRecord]:
        """Lookup records by source file path."""

        return self._records_for_ids(self._by_file_path.get(file_path, []))

    def to_json(self) -> str:
        """Serialize the table to JSON."""

        return json.dumps(
            [asdict(record) for record in self.records],
            sort_keys=True,
        )

    @classmethod
    def from_json(cls, payload: str) -> SymbolTable:
        """Deserialize a symbol table from JSON."""

        data = json.loads(payload)
        records = [SymbolRecord(**record) for record in data]
        return cls(records)

    def _records_for_ids(self, symbol_ids: list[str]) -> list[SymbolRecord]:
        return sorted(
            (self._records[symbol_id] for symbol_id in symbol_ids),
            key=lambda record: (
                record.qualified_name,
                record.file_path,
                record.start_line,
                record.end_line,
            ),
        )


class SymbolTableBuilder:
    """Build a global symbol table from extracted file symbols."""

    def build(self, files: list[SymbolTableInput]) -> SymbolTable:
        """Register all symbols from the provided files."""

        table = SymbolTable()
        for file_input in files:
            module = self._module_name(file_input.file_path)
            for symbol in file_input.symbols:
                self._register_symbol(
                    table,
                    symbol,
                    file_input.file_path,
                    module,
                    parent_symbol=None,
                )
        return table

    def _register_symbol(
        self,
        table: SymbolTable,
        symbol: Symbol,
        file_path: str,
        module: str,
        *,
        parent_symbol: str | None,
    ) -> None:
        record = self._record_for_symbol(
            symbol,
            file_path,
            module,
            parent_symbol=parent_symbol,
        )
        table.add(record)

        for child in symbol.children:
            self._register_symbol(
                table,
                child,
                file_path,
                module,
                parent_symbol=record.qualified_name,
            )

    def _record_for_symbol(
        self,
        symbol: Symbol,
        file_path: str,
        module: str,
        *,
        parent_symbol: str | None,
    ) -> SymbolRecord:
        qualified_name = self._qualified_name(symbol, module)
        short_name = self._short_name(symbol)

        return SymbolRecord(
            symbol_id=self._symbol_id(symbol, file_path, qualified_name),
            name=short_name,
            qualified_name=qualified_name,
            type=symbol.type,
            file_path=file_path,
            module=module,
            start_line=symbol.start_line,
            end_line=symbol.end_line,
            signature=symbol.signature,
            docstring=symbol.docstring,
            decorators=symbol.decorators,
            parent_symbol=parent_symbol,
            is_async=symbol.is_async,
            bases=symbol.bases,
        )

    def _qualified_name(self, symbol: Symbol, module: str) -> str:
        if symbol.type == "import":
            return f"{module}::<import>{symbol.name}"
        return f"{module}.{symbol.name}"

    def _short_name(self, symbol: Symbol) -> str:
        if symbol.type == "method":
            return symbol.name.rsplit(".", maxsplit=1)[-1]
        return symbol.name

    def _symbol_id(self, symbol: Symbol, file_path: str, qualified_name: str) -> str:
        return (
            f"{file_path}:{qualified_name}:{symbol.type}:"
            f"{symbol.start_line}:{symbol.end_line}"
        )

    def _module_name(self, file_path: str) -> str:
        path = Path(file_path)
        without_suffix = path.with_suffix("")
        if without_suffix.name == "__init__":
            without_suffix = without_suffix.parent
        return ".".join(without_suffix.parts)
