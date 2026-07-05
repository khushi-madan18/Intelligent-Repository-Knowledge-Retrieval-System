"""Build call graph edges from parsed ASTs and extracted symbols."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from reporag.ingestion.parser import ASTNodeData, ParsedAST
from reporag.ingestion.symbol_extractor import Symbol


@dataclass(frozen=True)
class CallGraphInput:
    """Parsed file data required for call graph construction."""

    file_path: str
    parsed: ParsedAST
    symbols: list[Symbol]


@dataclass(frozen=True)
class CallGraphEdge:
    """A directed call graph edge with call-site metadata."""

    caller: str
    callee: str
    call_site_file: str
    call_site_line: int
    call_text: str
    resolved: bool
    callee_file: str | None = None
    callee_line: int | None = None


@dataclass(frozen=True)
class _ResolvedTarget:
    symbol: Symbol
    file_path: str


class CallGraphBuilder:
    """Build caller -> callee edges from Tree-sitter AST nodes."""

    def build(self, files: list[CallGraphInput]) -> list[CallGraphEdge]:
        """Return call graph edges for the provided parsed files."""

        symbol_index = self._build_symbol_index(files)
        module_index = self._build_module_index(files)
        edges: list[CallGraphEdge] = []

        for file_input in files:
            flattened_symbols = self._flatten_symbols(file_input.symbols)
            caller_symbols = [
                symbol
                for symbol in flattened_symbols
                if symbol.type in {"function", "method", "class"}
            ]
            import_aliases = self._build_import_aliases(
                file_input.symbols,
                module_index,
            )

            for call_node in self._find_calls(file_input.parsed.root_node):
                caller = self._find_enclosing_symbol(call_node, caller_symbols)
                if caller is None:
                    continue

                callee_expression = self._call_expression(call_node)
                if not callee_expression:
                    continue

                target = self._resolve_target(
                    callee_expression,
                    caller,
                    file_input.file_path,
                    symbol_index,
                    module_index,
                    import_aliases,
                )
                edges.append(
                    self._edge(
                        caller=caller,
                        callee_expression=callee_expression,
                        call_node=call_node,
                        file_path=file_input.file_path,
                        target=target,
                    )
                )

        return sorted(
            edges,
            key=lambda edge: (
                edge.call_site_file,
                edge.call_site_line,
                edge.caller,
                edge.callee,
                edge.call_text,
            ),
        )

    def _edge(
        self,
        *,
        caller: Symbol,
        callee_expression: str,
        call_node: ASTNodeData,
        file_path: str,
        target: _ResolvedTarget | None,
    ) -> CallGraphEdge:
        if target is None:
            return CallGraphEdge(
                caller=caller.name,
                callee=callee_expression,
                call_site_file=file_path,
                call_site_line=call_node.start_line,
                call_text=call_node.text,
                resolved=False,
            )

        return CallGraphEdge(
            caller=caller.name,
            callee=target.symbol.name,
            call_site_file=file_path,
            call_site_line=call_node.start_line,
            call_text=call_node.text,
            resolved=True,
            callee_file=target.file_path,
            callee_line=target.symbol.start_line,
        )

    def _resolve_target(
        self,
        callee_expression: str,
        caller: Symbol,
        file_path: str,
        symbol_index: dict[str, list[_ResolvedTarget]],
        module_index: dict[str, str],
        import_aliases: dict[str, str],
    ) -> _ResolvedTarget | None:
        same_file_target = self._resolve_same_file(
            callee_expression,
            caller,
            file_path,
            symbol_index,
        )
        if same_file_target is not None:
            return same_file_target

        imported_target = self._resolve_imported(
            callee_expression,
            symbol_index,
            module_index,
            import_aliases,
        )
        if imported_target is not None:
            return imported_target

        return self._resolve_unique_name(callee_expression, symbol_index)

    def _resolve_same_file(
        self,
        callee_expression: str,
        caller: Symbol,
        file_path: str,
        symbol_index: dict[str, list[_ResolvedTarget]],
    ) -> _ResolvedTarget | None:
        candidates = self._candidate_names(callee_expression, caller)
        for candidate in candidates:
            for target in symbol_index.get(candidate, []):
                if target.file_path == file_path:
                    return target
        return None

    def _resolve_imported(
        self,
        callee_expression: str,
        symbol_index: dict[str, list[_ResolvedTarget]],
        module_index: dict[str, str],
        import_aliases: dict[str, str],
    ) -> _ResolvedTarget | None:
        parts = callee_expression.split(".")
        if not parts:
            return None

        alias = parts[0]
        imported_path = import_aliases.get(alias)
        if imported_path is None:
            return None

        imported_parts = imported_path.split(".")
        member_name = parts[-1] if len(parts) > 1 else imported_parts[-1]
        module_name = (
            ".".join(imported_parts[:-1]) if len(parts) == 1 else imported_path
        )
        target_file = module_index.get(module_name)

        if target_file is None and len(imported_parts) > 1:
            target_file = module_index.get(".".join(imported_parts[:-1]))

        for candidate in (member_name, callee_expression):
            for target in symbol_index.get(candidate, []):
                if target_file is None or target.file_path == target_file:
                    return target

        return None

    def _resolve_unique_name(
        self,
        callee_expression: str,
        symbol_index: dict[str, list[_ResolvedTarget]],
    ) -> _ResolvedTarget | None:
        candidates = self._candidate_names(callee_expression, caller=None)
        for candidate in candidates:
            targets = symbol_index.get(candidate, [])
            if len(targets) == 1:
                return targets[0]
        return None

    def _candidate_names(
        self,
        callee_expression: str,
        caller: Symbol | None,
    ) -> list[str]:
        candidates = [callee_expression]
        parts = callee_expression.split(".")
        last_part = parts[-1]

        if caller is not None and len(parts) == 2 and parts[0] in {"self", "cls"}:
            class_name = caller.name.rsplit(".", maxsplit=1)[0]
            if class_name != caller.name:
                candidates.append(f"{class_name}.{last_part}")

        candidates.append(last_part)
        return list(dict.fromkeys(candidates))

    def _find_enclosing_symbol(
        self,
        call_node: ASTNodeData,
        symbols: list[Symbol],
    ) -> Symbol | None:
        containing = [
            symbol
            for symbol in symbols
            if symbol.start_line <= call_node.start_line <= symbol.end_line
        ]
        if not containing:
            return None
        return max(
            containing,
            key=lambda symbol: (
                symbol.start_line,
                -1 * (symbol.end_line - symbol.start_line),
            ),
        )

    def _find_calls(self, node: ASTNodeData) -> list[ASTNodeData]:
        calls: list[ASTNodeData] = []
        if node.type == "call":
            calls.append(node)
        for child in node.children:
            calls.extend(self._find_calls(child))
        return calls

    def _call_expression(self, call_node: ASTNodeData) -> str:
        for child in call_node.children:
            if child.type != "argument_list":
                return child.text
        return ""

    def _build_symbol_index(
        self,
        files: list[CallGraphInput],
    ) -> dict[str, list[_ResolvedTarget]]:
        index: dict[str, list[_ResolvedTarget]] = {}
        for file_input in files:
            for symbol in self._flatten_symbols(file_input.symbols):
                if symbol.type == "import":
                    continue
                target = _ResolvedTarget(symbol=symbol, file_path=file_input.file_path)
                index.setdefault(symbol.name, []).append(target)
                short_name = symbol.name.rsplit(".", maxsplit=1)[-1]
                index.setdefault(short_name, []).append(target)
        return index

    def _build_module_index(self, files: list[CallGraphInput]) -> dict[str, str]:
        index: dict[str, str] = {}
        for file_input in files:
            path = Path(file_input.file_path)
            if path.suffix == ".py":
                module_name = ".".join(path.with_suffix("").parts)
                index[module_name] = file_input.file_path
                index[path.stem] = file_input.file_path
        return index

    def _build_import_aliases(
        self,
        symbols: list[Symbol],
        module_index: dict[str, str],
    ) -> dict[str, str]:
        aliases: dict[str, str] = {}

        for symbol in symbols:
            if symbol.type != "import":
                continue
            if symbol.is_from_import:
                for imported_name in symbol.imports:
                    alias = imported_name.alias or imported_name.name
                    aliases[alias] = f"{symbol.module}.{imported_name.name}"
                continue

            for imported_name in symbol.imports:
                alias = imported_name.alias or imported_name.name.split(".")[0]
                aliases[alias] = imported_name.name
                if imported_name.name not in module_index:
                    aliases[imported_name.name] = imported_name.name

        return aliases

    def _flatten_symbols(self, symbols: list[Symbol]) -> list[Symbol]:
        flattened: list[Symbol] = []
        for symbol in symbols:
            flattened.append(symbol)
            flattened.extend(self._flatten_symbols(symbol.children))
        return flattened
