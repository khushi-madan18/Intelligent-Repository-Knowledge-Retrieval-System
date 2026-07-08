"""Tests for graph-based retrieval."""

from src.reporag.graph.neo4j_store import GraphEdge, GraphNode, NetworkXGraphStore
from src.reporag.retrieval.graph_traversal import (
    GraphTraversalRetriever,
    RetrievalResult,
)


def build_store() -> NetworkXGraphStore:
    store = NetworkXGraphStore()
    store.bulk_insert_nodes(
        [
            GraphNode(
                "module:app.service",
                "Module",
                {
                    "name": "app.service",
                    "qualified_name": "app.service",
                    "file_path": "app/service.py",
                },
            ),
            GraphNode(
                "fn:app.service.run",
                "Function",
                {
                    "name": "run",
                    "qualified_name": "app.service.run",
                    "type": "function",
                    "file_path": "app/service.py",
                    "start_line": 3,
                    "end_line": 5,
                    "signature": "def run():",
                },
            ),
            GraphNode(
                "fn:app.service.helper",
                "Function",
                {
                    "name": "helper",
                    "qualified_name": "app.service.helper",
                    "type": "function",
                    "file_path": "app/service.py",
                    "start_line": 7,
                    "end_line": 8,
                    "signature": "def helper():",
                },
            ),
            GraphNode(
                "fn:app.db.save",
                "Function",
                {
                    "name": "save",
                    "qualified_name": "app.db.save",
                    "type": "function",
                    "file_path": "app/db.py",
                    "start_line": 10,
                    "end_line": 12,
                    "signature": "def save():",
                },
            ),
        ]
    )
    store.bulk_insert_edges(
        [
            GraphEdge("module:app.service", "fn:app.service.run", "CONTAINS"),
            GraphEdge(
                "fn:app.service.run",
                "fn:app.service.helper",
                "CALLS",
                {"call_site_line": 4},
            ),
            GraphEdge(
                "fn:app.service.helper",
                "fn:app.db.save",
                "CALLS",
                {"call_site_line": 8},
            ),
        ]
    )
    return store


def test_n_hop_neighbor_query_is_correct() -> None:
    retriever = GraphTraversalRetriever(build_store())

    response = retriever.neighbors("fn:app.service.run", hops=2, direction="out")

    assert [result.id for result in response.results] == [
        "fn:app.service.helper",
        "fn:app.db.save",
    ]
    assert response.results[0].payload["distance"] == 1
    assert response.results[1].payload["distance"] == 2
    assert {edge["type"] for edge in response.edges} == {"CALLS"}


def test_shortest_path_between_symbols() -> None:
    retriever = GraphTraversalRetriever(build_store())

    result = retriever.shortest_path("fn:app.service.run", "fn:app.db.save")

    assert result is not None
    assert result.path == [
        "fn:app.service.run",
        "fn:app.service.helper",
        "fn:app.db.save",
    ]
    assert result.payload["path_length"] == 2
    assert len(result.edges) == 2


def test_subgraph_extraction_around_symbol_set() -> None:
    retriever = GraphTraversalRetriever(build_store())

    response = retriever.subgraph(
        ["fn:app.service.run", "fn:app.db.save"],
        hops=1,
        direction="both",
    )

    node_ids = {node["id"] for node in response.nodes}
    assert node_ids == {
        "module:app.service",
        "fn:app.service.run",
        "fn:app.service.helper",
        "fn:app.db.save",
    }
    assert response.results[0].result_type == "subgraph"
    assert len(response.results[0].nodes) == 4


def test_edge_type_filtering() -> None:
    retriever = GraphTraversalRetriever(build_store())

    response = retriever.neighbors(
        "fn:app.service.run",
        hops=1,
        direction="both",
        edge_types={"CONTAINS"},
    )

    assert [result.id for result in response.results] == ["module:app.service"]


def test_graph_results_use_common_retrieval_result_schema() -> None:
    retriever = GraphTraversalRetriever(build_store())

    result = retriever.neighbors("fn:app.service.run", hops=1, direction="out").results[
        0
    ]

    assert isinstance(result, RetrievalResult)
    assert result.file_path == "app/service.py"
    assert result.start_line == 7
    assert result.end_line == 8
    assert result.symbol == "app.service.helper"
    assert result.symbol_type == "function"
    assert result.text == "def helper():"


def test_missing_path_returns_none() -> None:
    store = build_store()
    store.create_node(GraphNode("fn:isolated", "Function", {"name": "isolated"}))
    retriever = GraphTraversalRetriever(store)

    assert retriever.shortest_path("fn:isolated", "fn:app.db.save") is None


def test_missing_symbol_returns_empty_neighbors() -> None:
    retriever = GraphTraversalRetriever(build_store())

    response = retriever.neighbors("fn:missing", hops=2)

    assert response.results == []
    assert response.nodes == []
    assert response.edges == []
