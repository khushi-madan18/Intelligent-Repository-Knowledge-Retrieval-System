from __future__ import annotations

from typing import Any

from reporag.graph.call_graph import CallGraphBuilder, CallGraphInput
from reporag.graph.dependency_graph import DependencyGraphBuilder, DependencyGraphInput
from reporag.graph.neo4j_store import (
    GraphEdge,
    GraphNode,
    Neo4jGraphStore,
    NetworkXGraphStore,
    calls_edge,
    imports_edge,
    load_symbol_table,
)
from reporag.graph.symbol_table import SymbolTableBuilder, SymbolTableInput
from reporag.ingestion.parser import ASTParser
from reporag.ingestion.symbol_extractor import SymbolExtractor


def analyze(
    file_path: str, source: str
) -> tuple[CallGraphInput, DependencyGraphInput, SymbolTableInput]:
    parsed = ASTParser().parse(source, language="python")
    symbols = SymbolExtractor().extract(parsed, file_path)
    return (
        CallGraphInput(file_path=file_path, parsed=parsed, symbols=symbols),
        DependencyGraphInput(file_path=file_path, symbols=symbols),
        SymbolTableInput(file_path=file_path, symbols=symbols),
    )


def test_networkx_store_creates_queries_and_clears_nodes_and_edges() -> None:
    store = NetworkXGraphStore()

    store.create_node(
        GraphNode("module:app.service", "Module", {"name": "app.service"})
    )
    store.create_node(GraphNode("fn:hello", "Function", {"name": "hello"}))
    store.create_edge(
        GraphEdge(
            "module:app.service",
            "fn:hello",
            "CONTAINS",
            {"child": "app.service.hello"},
        )
    )

    assert store.query("MATCH (n {id: $id}) RETURN n", {"id": "fn:hello"}) == [
        {"n": {"id": "fn:hello", "label": "Function", "name": "hello"}}
    ]
    assert store.outgoing("module:app.service", "CONTAINS") == [
        ("fn:hello", {"type": "CONTAINS", "child": "app.service.hello"})
    ]
    assert len(store.query("MATCH (a)-[r]->(b) RETURN a, r, b")) == 1

    store.clear()

    assert store.query("MATCH (n) RETURN n") == []


def test_loads_symbol_table_nodes_contains_and_inherits_edges() -> None:
    _, _, base_input = analyze("app/base.py", "class Base:\n    pass\n")
    _, _, service_input = analyze(
        "app/service.py",
        """class Service(Base):
    def run(self):
        return 42
""",
    )
    table = SymbolTableBuilder().build([base_input, service_input])
    store = NetworkXGraphStore()

    load_symbol_table(store, table)

    service = table.lookup_qualified("app.service.Service")[0]
    run = table.lookup_qualified("app.service.Service.run")[0]
    base = table.lookup_qualified("app.base.Base")[0]

    assert store.get_node(service.symbol_id)["label"] == "Class"
    assert store.get_node(run.symbol_id)["label"] == "Function"
    assert (
        run.symbol_id,
        {"type": "CONTAINS", "child": run.qualified_name},
    ) in store.outgoing(
        service.symbol_id,
        "CONTAINS",
    )
    assert store.outgoing(service.symbol_id, "INHERITS") == [
        (base.symbol_id, {"type": "INHERITS", "base": "Base"})
    ]


def test_converts_call_and_import_edges_to_store_edges() -> None:
    call_input, dep_input, symbol_input = analyze(
        "app/service.py",
        """import app.helpers

def run(value):
    return helper(value)

def helper(value):
    return value
""",
    )
    table = SymbolTableBuilder().build([symbol_input])
    call_graph_edges = CallGraphBuilder().build([call_input])
    dependency_edges = DependencyGraphBuilder().build([dep_input]).edges
    store = NetworkXGraphStore()

    load_symbol_table(store, table)
    call_store_edge = calls_edge(call_graph_edges[0], table)
    assert call_store_edge is not None
    store.create_edge(call_store_edge)
    store.create_node(
        GraphNode("module:app.helpers", "Module", {"name": "app.helpers"})
    )
    store.create_edge(imports_edge(dependency_edges[0]))

    run = table.lookup_qualified("app.service.run")[0]
    helper = table.lookup_qualified("app.service.helper")[0]

    assert store.outgoing(run.symbol_id, "CALLS") == [
        (
            helper.symbol_id,
            {
                "type": "CALLS",
                "call_site_file": "app/service.py",
                "call_site_line": 4,
                "call_text": "helper(value)",
            },
        )
    ]
    assert store.outgoing("module:app.service", "IMPORTS") == [
        (
            "module:app.helpers",
            {
                "type": "IMPORTS",
                "import_type": "import",
                "imported_names": ["app.helpers"],
                "source_file": "app/service.py",
                "target_file": "",
                "resolved": False,
            },
        )
    ]


def test_networkx_bulk_insert_handles_10000_nodes() -> None:
    store = NetworkXGraphStore()
    nodes = [
        GraphNode(f"fn:{index}", "Function", {"name": f"fn_{index}"})
        for index in range(10_000)
    ]

    store.bulk_insert_nodes(nodes)

    assert store.get_node("fn:9999") == {
        "id": "fn:9999",
        "label": "Function",
        "name": "fn_9999",
    }
    assert len(store.query("MATCH (n) RETURN n")) == 10_000


class CapturingNeo4jStore(Neo4jGraphStore):
    def __init__(self) -> None:
        super().__init__(
            uri="bolt://example:7687",
            user="neo4j",
            password="password",
        )
        self.calls: list[tuple[str, dict[str, Any] | None]] = []

    def query(
        self,
        cypher: str,
        parameters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        self.calls.append((" ".join(cypher.split()), parameters))
        return []


def test_neo4j_store_bulk_insert_builds_parameterized_cypher() -> None:
    store = CapturingNeo4jStore()

    store.bulk_insert_nodes(
        [GraphNode("fn:hello", "Function", {"qualified_name": "app.hello"})]
    )
    store.bulk_insert_edges(
        [GraphEdge("fn:hello", "fn:world", "CALLS", {"call_site_line": 3})]
    )

    node_cypher, node_parameters = store.calls[0]
    edge_cypher, edge_parameters = store.calls[1]

    assert "MERGE (n:Function {id: row.id})" in node_cypher
    assert node_parameters == {
        "rows": [{"id": "fn:hello", "qualified_name": "app.hello"}]
    }
    assert "MERGE (source)-[r:CALLS]->(target)" in edge_cypher
    assert edge_parameters == {
        "rows": [
            {
                "source_id": "fn:hello",
                "target_id": "fn:world",
                "properties": {"call_site_line": 3},
            }
        ]
    }
