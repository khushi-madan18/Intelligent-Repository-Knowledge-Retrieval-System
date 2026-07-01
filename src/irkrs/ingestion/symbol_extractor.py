"""Extract code symbols from Python ASTs."""

from __future__ import annotations

import ast
from dataclasses import dataclass, field

from irkrs.ingestion.parser import ParsedPythonFile


@dataclass(frozen=True)
class Symbol:
    """A named code element with source location metadata."""

    name: str
    qualified_name: str
    kind: str
    path: str
    start_line: int
    end_line: int
    signature: str = ""
    docstring: str | None = None
    parent: str | None = None
    imports: tuple[str, ...] = field(default_factory=tuple)


class SymbolExtractor(ast.NodeVisitor):
    """Extract functions, classes, methods, and imports."""

    def __init__(self, parsed_file: ParsedPythonFile) -> None:
        self.parsed_file = parsed_file
        self.symbols: list[Symbol] = []
        self._scope: list[str] = []

    def extract(self) -> list[Symbol]:
        self.visit(self.parsed_file.tree)
        return self.symbols

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        qualified_name = self._qualified_name(node.name)
        bases = tuple(self._expr_name(base) for base in node.bases)
        self.symbols.append(
            Symbol(
                name=node.name,
                qualified_name=qualified_name,
                kind="class",
                path=self.parsed_file.path,
                start_line=node.lineno,
                end_line=getattr(node, "end_lineno", node.lineno),
                signature=self._class_signature(node),
                docstring=ast.get_docstring(node),
                parent=self._parent,
                imports=bases,
            )
        )
        self._scope.append(node.name)
        self.generic_visit(node)
        self._scope.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._add_function(node, "method" if self._scope else "function")
        self._scope.append(node.name)
        self.generic_visit(node)
        self._scope.pop()

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._add_function(node, "async_method" if self._scope else "async_function")
        self._scope.append(node.name)
        self.generic_visit(node)
        self._scope.pop()

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.symbols.append(self._import_symbol(alias.name, node.lineno))

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = "." * node.level + (node.module or "")
        for alias in node.names:
            imported = f"{module}.{alias.name}" if module else alias.name
            self.symbols.append(self._import_symbol(imported, node.lineno))

    @property
    def _parent(self) -> str | None:
        return ".".join(self._scope) if self._scope else None

    def _qualified_name(self, name: str) -> str:
        return ".".join([*self._scope, name])

    def _add_function(
        self, node: ast.FunctionDef | ast.AsyncFunctionDef, kind: str
    ) -> None:
        self.symbols.append(
            Symbol(
                name=node.name,
                qualified_name=self._qualified_name(node.name),
                kind=kind,
                path=self.parsed_file.path,
                start_line=node.lineno,
                end_line=getattr(node, "end_lineno", node.lineno),
                signature=self._function_signature(node),
                docstring=ast.get_docstring(node),
                parent=self._parent,
            )
        )

    def _import_symbol(self, imported_name: str, line: int) -> Symbol:
        return Symbol(
            name=imported_name.rsplit(".", 1)[-1],
            qualified_name=imported_name,
            kind="import",
            path=self.parsed_file.path,
            start_line=line,
            end_line=line,
            imports=(imported_name,),
        )

    def _function_signature(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
        args = [arg.arg for arg in node.args.posonlyargs + node.args.args]
        if node.args.vararg is not None:
            args.append(f"*{node.args.vararg.arg}")
        args.extend(arg.arg for arg in node.args.kwonlyargs)
        if node.args.kwarg is not None:
            args.append(f"**{node.args.kwarg.arg}")
        prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
        return f"{prefix} {node.name}({', '.join(args)})"

    def _class_signature(self, node: ast.ClassDef) -> str:
        bases = ", ".join(self._expr_name(base) for base in node.bases)
        return f"class {node.name}({bases})" if bases else f"class {node.name}"

    def _expr_name(self, node: ast.AST) -> str:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            value = self._expr_name(node.value)
            return f"{value}.{node.attr}" if value else node.attr
        if isinstance(node, ast.Subscript):
            return self._expr_name(node.value)
        return ast.unparse(node) if hasattr(ast, "unparse") else ""
