"""Extract meaningful code symbols from parsed AST nodes."""

from __future__ import annotations

import ast
from dataclasses import dataclass, field

from reporag.ingestion.parser import ASTNodeData, ParsedAST


class SymbolExtractionError(ValueError):
    """Raised when symbols cannot be extracted for a parsed language."""


@dataclass(frozen=True)
class ImportName:
    """One imported name and its optional alias."""

    name: str
    alias: str | None = None


@dataclass(frozen=True)
class Symbol:
    """A meaningful code entity extracted from a source file."""

    name: str
    type: str
    file_path: str
    start_line: int
    end_line: int
    signature: str = ""
    docstring: str = ""
    decorators: list[str] = field(default_factory=list)
    is_async: bool = False
    children: list[Symbol] = field(default_factory=list)
    bases: list[str] = field(default_factory=list)
    module: str = ""
    imports: list[ImportName] = field(default_factory=list)
    is_from_import: bool = False
    is_static: bool = False
    is_classmethod: bool = False
    is_property: bool = False


class SymbolExtractor:
    """Extract functions, classes, methods, and imports from parsed ASTs."""

    def extract(self, parsed: ParsedAST, file_path: str) -> list[Symbol]:
        """Return symbols found in a parsed source file."""

        if parsed.language not in {"py", "python"}:
            raise SymbolExtractionError(
                f"Symbol extraction is not supported for {parsed.language}"
            )

        symbols: list[Symbol] = []
        self._walk(parsed.root_node, file_path, symbols, parent_class=None)
        return symbols

    def _walk(
        self,
        node: ASTNodeData,
        file_path: str,
        symbols: list[Symbol],
        *,
        parent_class: str | None,
    ) -> None:
        if node.type == "ERROR":
            return

        symbol_node_types = {
            "class_definition",
            "function_definition",
            "async_function_definition",
            "import_statement",
            "import_from_statement",
        }
        if node.has_error and node.type in symbol_node_types:
            return

        if node.type == "decorated_definition":
            symbol = self._extract_decorated(node, file_path, parent_class=parent_class)
            if symbol is not None:
                symbols.append(symbol)
            return

        if node.type in {"function_definition", "async_function_definition"}:
            symbols.append(
                self._extract_function(
                    node,
                    file_path,
                    decorators=[],
                    parent_class=parent_class,
                )
            )
            return

        if node.type == "class_definition":
            symbols.append(self._extract_class(node, file_path, decorators=[]))
            return

        if node.type in {"import_statement", "import_from_statement"}:
            symbols.append(self._extract_import(node, file_path))
            return

        for child in node.children:
            self._walk(child, file_path, symbols, parent_class=parent_class)

    def _extract_decorated(
        self,
        node: ASTNodeData,
        file_path: str,
        *,
        parent_class: str | None,
    ) -> Symbol | None:
        decorators = [
            child.text.strip() for child in node.children if child.type == "decorator"
        ]
        definition = next(
            (
                child
                for child in node.children
                if child.type
                in {
                    "class_definition",
                    "function_definition",
                    "async_function_definition",
                }
            ),
            None,
        )

        if definition is None or definition.has_error:
            return None
        if definition.type == "class_definition":
            return self._extract_class(definition, file_path, decorators=decorators)
        return self._extract_function(
            definition,
            file_path,
            decorators=decorators,
            parent_class=parent_class,
        )

    def _extract_class(
        self,
        node: ASTNodeData,
        file_path: str,
        *,
        decorators: list[str],
    ) -> Symbol:
        name = self._first_direct_child_text(node, "identifier")
        children = self._extract_class_children(node, file_path, class_name=name)
        return Symbol(
            name=name,
            type="class",
            file_path=file_path,
            start_line=node.start_line,
            end_line=node.end_line,
            signature=self._signature(node),
            docstring=self._docstring(node),
            decorators=decorators,
            children=children,
            bases=self._class_bases(node),
        )

    def _extract_class_children(
        self,
        node: ASTNodeData,
        file_path: str,
        *,
        class_name: str,
    ) -> list[Symbol]:
        block = self._first_direct_child(node, "block")
        if block is None:
            return []

        methods: list[Symbol] = []
        for child in block.children:
            if child.type == "ERROR":
                continue
            if child.type == "decorated_definition":
                method = self._extract_decorated(
                    child,
                    file_path,
                    parent_class=class_name,
                )
                if method is not None:
                    methods.append(method)
            elif child.type in {"function_definition", "async_function_definition"}:
                methods.append(
                    self._extract_function(
                        child,
                        file_path,
                        decorators=[],
                        parent_class=class_name,
                    )
                )
        return methods

    def _extract_function(
        self,
        node: ASTNodeData,
        file_path: str,
        *,
        decorators: list[str],
        parent_class: str | None,
    ) -> Symbol:
        raw_name = self._first_direct_child_text(node, "identifier")
        symbol_type = "method" if parent_class else "function"
        name = f"{parent_class}.{raw_name}" if parent_class else raw_name

        return Symbol(
            name=name,
            type=symbol_type,
            file_path=file_path,
            start_line=node.start_line,
            end_line=node.end_line,
            signature=self._signature(node),
            docstring=self._docstring(node),
            decorators=decorators,
            is_async=self._is_async(node),
            is_static="@staticmethod" in decorators,
            is_classmethod="@classmethod" in decorators,
            is_property="@property" in decorators,
        )

    def _extract_import(self, node: ASTNodeData, file_path: str) -> Symbol:
        if node.type == "import_from_statement":
            module, names = self._parse_from_import(node.text)
            return Symbol(
                name=module,
                type="import",
                file_path=file_path,
                start_line=node.start_line,
                end_line=node.end_line,
                module=module,
                imports=names,
                is_from_import=True,
            )

        names = self._parse_import(node.text)
        return Symbol(
            name=", ".join(import_name.name for import_name in names),
            type="import",
            file_path=file_path,
            start_line=node.start_line,
            end_line=node.end_line,
            imports=names,
            is_from_import=False,
        )

    def _signature(self, node: ASTNodeData) -> str:
        first_line = node.text.strip().splitlines()[0].strip()
        return first_line.removesuffix(":")

    def _docstring(self, node: ASTNodeData) -> str:
        block = self._first_direct_child(node, "block")
        if block is None:
            return ""

        for child in block.children:
            if child.type in {":", "comment"}:
                continue
            string_node = self._first_descendant(child, "string")
            if string_node is None:
                return ""
            return self._parse_string_literal(string_node.text.strip())

        return ""

    def _class_bases(self, node: ASTNodeData) -> list[str]:
        argument_list = self._first_direct_child(node, "argument_list")
        if argument_list is None:
            return []
        return [
            child.text.strip()
            for child in argument_list.children
            if child.type not in {"(", ")", ","}
        ]

    def _parse_import(self, text: str) -> list[ImportName]:
        import_text = text.removeprefix("import").strip()
        return [self._parse_import_name(part) for part in self._split_csv(import_text)]

    def _parse_from_import(self, text: str) -> tuple[str, list[ImportName]]:
        without_from = text.removeprefix("from").strip()
        module, _, import_text = without_from.partition(" import ")
        return module.strip(), [
            self._parse_import_name(part) for part in self._split_csv(import_text)
        ]

    def _parse_import_name(self, text: str) -> ImportName:
        name, separator, alias = text.strip().partition(" as ")
        return ImportName(name=name.strip(), alias=alias.strip() if separator else None)

    def _split_csv(self, text: str) -> list[str]:
        return [part.strip() for part in text.split(",") if part.strip()]

    def _is_async(self, node: ASTNodeData) -> bool:
        return (
            node.type == "async_function_definition"
            or node.text.lstrip().startswith("async def ")
        )

    def _first_direct_child(
        self,
        node: ASTNodeData,
        child_type: str,
    ) -> ASTNodeData | None:
        return next(
            (child for child in node.children if child.type == child_type),
            None,
        )

    def _first_direct_child_text(self, node: ASTNodeData, child_type: str) -> str:
        child = self._first_direct_child(node, child_type)
        return child.text if child is not None else ""

    def _first_descendant(
        self,
        node: ASTNodeData,
        node_type: str,
    ) -> ASTNodeData | None:
        if node.type == node_type:
            return node
        for child in node.children:
            found = self._first_descendant(child, node_type)
            if found is not None:
                return found
        return None

    def _parse_string_literal(self, text: str) -> str:
        try:
            value = ast.literal_eval(text)
        except (SyntaxError, ValueError):
            return text
        return value if isinstance(value, str) else text
