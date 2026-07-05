"""Build module import dependency graphs from extracted import symbols."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from reporag.ingestion.symbol_extractor import ImportName, Symbol


@dataclass(frozen=True)
class DependencyGraphInput:
    """Symbols extracted from one source file."""

    file_path: str
    symbols: list[Symbol]


@dataclass(frozen=True)
class DependencyEdge:
    """Directed module dependency edge with import metadata."""

    source: str
    target: str
    import_type: str
    imported_names: list[str]
    source_file: str
    target_file: str | None = None
    resolved: bool = False
    is_star_import: bool = False
    warning: str | None = None


@dataclass(frozen=True)
class CircularImport:
    """A detected circular import chain."""

    chain: list[str]


@dataclass(frozen=True)
class DependencyGraph:
    """Import dependency graph result."""

    edges: list[DependencyEdge] = field(default_factory=list)
    circular_imports: list[CircularImport] = field(default_factory=list)


class DependencyGraphBuilder:
    """Build module-level dependency edges from Python import symbols."""

    def build(self, files: list[DependencyGraphInput]) -> DependencyGraph:
        """Return dependency graph edges and circular import chains."""

        module_to_file = {
            self._module_name(file_input.file_path): file_input.file_path
            for file_input in files
        }
        edges: list[DependencyEdge] = []

        for file_input in files:
            source_module = self._module_name(file_input.file_path)
            for symbol in file_input.symbols:
                if symbol.type != "import":
                    continue
                edges.extend(
                    self._edges_for_import(
                        symbol,
                        source_module,
                        file_input.file_path,
                        module_to_file,
                    )
                )

        return DependencyGraph(
            edges=sorted(
                edges,
                key=lambda edge: (
                    edge.source,
                    edge.target,
                    edge.import_type,
                    edge.imported_names,
                ),
            ),
            circular_imports=self._detect_cycles(edges, module_to_file),
        )

    def _edges_for_import(
        self,
        symbol: Symbol,
        source_module: str,
        source_file: str,
        module_to_file: dict[str, str],
    ) -> list[DependencyEdge]:
        if symbol.is_from_import:
            return self._from_import_edges(
                symbol,
                source_module,
                source_file,
                module_to_file,
            )
        return self._import_edges(symbol, source_module, source_file, module_to_file)

    def _import_edges(
        self,
        symbol: Symbol,
        source_module: str,
        source_file: str,
        module_to_file: dict[str, str],
    ) -> list[DependencyEdge]:
        edges: list[DependencyEdge] = []
        for imported_name in symbol.imports:
            target = self._resolve_absolute_or_external(imported_name.name)
            edges.append(
                self._edge(
                    source=source_module,
                    target=target,
                    import_type="import",
                    imported_names=[imported_name.name],
                    source_file=source_file,
                    module_to_file=module_to_file,
                )
            )
        return edges

    def _from_import_edges(
        self,
        symbol: Symbol,
        source_module: str,
        source_file: str,
        module_to_file: dict[str, str],
    ) -> list[DependencyEdge]:
        target_base = self._resolve_module(symbol.module, source_module)
        is_package_relative = symbol.module.strip(".") == ""
        grouped_imports: dict[str, list[ImportName]] = {}

        for imported_name in symbol.imports:
            target = (
                f"{target_base}.{imported_name.name}"
                if is_package_relative
                else target_base
            )
            submodule_target = f"{target_base}.{imported_name.name}"
            if (
                not is_package_relative
                and imported_name.name != "*"
                and submodule_target in module_to_file
            ):
                target = submodule_target
            grouped_imports.setdefault(target, []).append(imported_name)

        edges: list[DependencyEdge] = []
        for target, imported_names in grouped_imports.items():
            is_star = any(imported_name.name == "*" for imported_name in imported_names)
            display_names = [
                self._import_display(imported_name) for imported_name in imported_names
            ]
            edges.append(
                self._edge(
                    source=source_module,
                    target=target,
                    import_type="from_import",
                    imported_names=display_names,
                    source_file=source_file,
                    module_to_file=module_to_file,
                    is_star_import=is_star,
                    warning=(
                        f"Star import from {target_base} makes dependencies implicit"
                        if is_star
                        else None
                    ),
                )
            )

        return edges

    def _edge(
        self,
        *,
        source: str,
        target: str,
        import_type: str,
        imported_names: list[str],
        source_file: str,
        module_to_file: dict[str, str],
        is_star_import: bool = False,
        warning: str | None = None,
    ) -> DependencyEdge:
        target_file = module_to_file.get(target)
        return DependencyEdge(
            source=source,
            target=target,
            import_type=import_type,
            imported_names=imported_names,
            source_file=source_file,
            target_file=target_file,
            resolved=target_file is not None,
            is_star_import=is_star_import,
            warning=warning,
        )

    def _detect_cycles(
        self,
        edges: list[DependencyEdge],
        module_to_file: dict[str, str],
    ) -> list[CircularImport]:
        adjacency: dict[str, set[str]] = {module: set() for module in module_to_file}
        for edge in edges:
            if edge.source in module_to_file and edge.target in module_to_file:
                adjacency.setdefault(edge.source, set()).add(edge.target)

        cycles: list[CircularImport] = []
        seen_cycles: set[tuple[str, ...]] = set()

        def visit(node: str, path: list[str]) -> None:
            if node in path:
                cycle = path[path.index(node) :] + [node]
                key = self._cycle_key(cycle)
                if key not in seen_cycles:
                    seen_cycles.add(key)
                    cycles.append(CircularImport(chain=cycle))
                return

            for next_node in sorted(adjacency.get(node, set())):
                visit(next_node, [*path, node])

        for module in sorted(adjacency):
            visit(module, [])

        return sorted(cycles, key=lambda cycle: cycle.chain)

    def _cycle_key(self, cycle: list[str]) -> tuple[str, ...]:
        nodes = cycle[:-1]
        rotations = [
            tuple(nodes[index:] + nodes[:index]) for index in range(len(nodes))
        ]
        canonical = min(rotations)
        return (*canonical, canonical[0])

    def _resolve_module(self, module: str, source_module: str) -> str:
        if not module.startswith("."):
            return module

        level = len(module) - len(module.lstrip("."))
        suffix = module[level:]
        package_parts = source_module.split(".")[:-1]
        base_parts = package_parts[: max(0, len(package_parts) - level + 1)]
        if suffix:
            base_parts.extend(suffix.split("."))
        return ".".join(part for part in base_parts if part)

    def _resolve_absolute_or_external(self, module: str) -> str:
        return module

    def _module_name(self, file_path: str) -> str:
        path = Path(file_path)
        without_suffix = path.with_suffix("")
        if without_suffix.name == "__init__":
            without_suffix = without_suffix.parent
        return ".".join(without_suffix.parts)

    def _import_display(self, imported_name: ImportName) -> str:
        if imported_name.alias:
            return f"{imported_name.name} as {imported_name.alias}"
        return imported_name.name
