"""Graph-based retrieval for symbol neighbors, paths, and subgraphs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

import networkx as nx


class GraphQueryStore(Protocol):
    """Minimal graph store interface used by GraphTraversalRetriever."""

    def query(
        self,
        cypher: str,
        parameters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Run a graph query and return rows."""


@dataclass(frozen=True)
class RetrievalResult:
    """Common retrieval result schema for graph, vector, and sparse retrieval."""

    id: str
    score: float
    payload: dict[str, Any]
    result_type: str
    file_path: str | None = None
    start_line: int | None = None
    end_line: int | None = None
    symbol: str | None = None
    symbol_type: str | None = None
    text: str = ""
    nodes: list[dict[str, Any]] = field(default_factory=list)
    edges: list[dict[str, Any]] = field(default_factory=list)
    path: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class GraphTraversalResponse:
    """Graph retrieval response."""

    results: list[RetrievalResult]
    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]


class GraphTraversalRetriever:
    """Retrieve structural context from a code graph."""

    def __init__(self, store: GraphQueryStore) -> None:
        self.store = store

    def neighbors(
        self,
        symbol_id: str,
        *,
        hops: int = 1,
        direction: str = "both",
        edge_types: set[str] | None = None,
    ) -> GraphTraversalResponse:
        """Return N-hop neighbors around a symbol."""

        if hops < 1:
            raise ValueError("hops must be at least 1")
        graph = self._load_graph()
        if symbol_id not in graph:
            return GraphTraversalResponse(results=[], nodes=[], edges=[])

        distances = self._distances(
            graph,
            symbol_id,
            hops=hops,
            direction=direction,
            edge_types=edge_types,
        )
        neighbor_ids = {node_id for node_id in distances if node_id != symbol_id}
        subgraph_node_ids = neighbor_ids | {symbol_id}
        edges = self._edges_between(graph, subgraph_node_ids, edge_types=edge_types)
        results = [
            self._node_result(
                graph,
                node_id,
                result_type="neighbor",
                score=1.0 / distances[node_id],
                extra_payload={"distance": distances[node_id], "source_id": symbol_id},
            )
            for node_id in sorted(
                neighbor_ids, key=lambda item: (distances[item], item)
            )
        ]
        return GraphTraversalResponse(
            results=results,
            nodes=self._nodes_payload(graph, subgraph_node_ids),
            edges=edges,
        )

    def shortest_path(
        self,
        source_id: str,
        target_id: str,
        *,
        edge_types: set[str] | None = None,
    ) -> RetrievalResult | None:
        """Return the shortest directed path between two symbols."""

        graph = self._load_graph()
        filtered = self._filtered_graph(graph, edge_types=edge_types)
        try:
            path = nx.shortest_path(filtered, source_id, target_id)
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return None

        path_node_ids = set(path)
        edges = self._path_edges(filtered, path)
        nodes = self._nodes_payload(filtered, path_node_ids)
        payload = {
            "source_id": source_id,
            "target_id": target_id,
            "path": path,
            "path_length": len(path) - 1,
            "nodes": nodes,
            "edges": edges,
        }
        return RetrievalResult(
            id=f"path:{source_id}->{target_id}",
            score=1.0 / max(len(path) - 1, 1),
            payload=payload,
            result_type="path",
            symbol=target_id,
            nodes=nodes,
            edges=edges,
            path=path,
            text=" -> ".join(path),
        )

    def subgraph(
        self,
        symbol_ids: list[str],
        *,
        hops: int = 1,
        direction: str = "both",
        edge_types: set[str] | None = None,
    ) -> GraphTraversalResponse:
        """Extract a subgraph around a set of symbols."""

        if hops < 0:
            raise ValueError("hops must be at least 0")
        graph = self._load_graph()
        included: set[str] = {
            symbol_id for symbol_id in symbol_ids if symbol_id in graph
        }

        for symbol_id in list(included):
            distances = self._distances(
                graph,
                symbol_id,
                hops=hops,
                direction=direction,
                edge_types=edge_types,
            )
            included.update(distances)

        edges = self._edges_between(graph, included, edge_types=edge_types)
        nodes = self._nodes_payload(graph, included)
        result = RetrievalResult(
            id="subgraph:" + ",".join(symbol_ids),
            score=float(len(included)),
            payload={
                "seed_symbol_ids": list(symbol_ids),
                "nodes": nodes,
                "edges": edges,
            },
            result_type="subgraph",
            nodes=nodes,
            edges=edges,
            text=f"{len(nodes)} nodes, {len(edges)} edges",
        )
        return GraphTraversalResponse(results=[result], nodes=nodes, edges=edges)

    def _load_graph(self) -> nx.MultiDiGraph:
        graph = nx.MultiDiGraph()

        for row in self.store.query("MATCH (n) RETURN n"):
            node = self._normalize_node(row["n"])
            node_id = str(node.get("id"))
            graph.add_node(node_id, **node)

        for row in self.store.query("MATCH (a)-[r]->(b) RETURN a, r, b"):
            source = self._normalize_node(row["a"])
            target = self._normalize_node(row["b"])
            edge = self._normalize_edge(row["r"])
            source_id = str(source.get("id"))
            target_id = str(target.get("id"))
            graph.add_node(source_id, **source)
            graph.add_node(target_id, **target)
            graph.add_edge(
                source_id,
                target_id,
                key=edge.get("type"),
                **edge,
            )

        return graph

    def _distances(
        self,
        graph: nx.MultiDiGraph,
        source_id: str,
        *,
        hops: int,
        direction: str,
        edge_types: set[str] | None,
    ) -> dict[str, int]:
        filtered = self._filtered_graph(graph, edge_types=edge_types)
        traversal_graph = self._directional_graph(filtered, direction)
        lengths = nx.single_source_shortest_path_length(
            traversal_graph,
            source_id,
            cutoff=hops,
        )
        return dict(lengths)

    def _filtered_graph(
        self,
        graph: nx.MultiDiGraph,
        *,
        edge_types: set[str] | None,
    ) -> nx.MultiDiGraph:
        if edge_types is None:
            return graph.copy()

        filtered = nx.MultiDiGraph()
        filtered.add_nodes_from(graph.nodes(data=True))
        for source, target, key, data in graph.edges(keys=True, data=True):
            if data.get("type") in edge_types:
                filtered.add_edge(source, target, key=key, **data)
        return filtered

    def _directional_graph(
        self,
        graph: nx.MultiDiGraph,
        direction: str,
    ) -> nx.Graph | nx.DiGraph:
        if direction == "out":
            return nx.DiGraph(graph)
        if direction == "in":
            return nx.DiGraph(graph.reverse(copy=True))
        if direction == "both":
            return nx.Graph(graph)
        raise ValueError("direction must be one of: out, in, both")

    def _edges_between(
        self,
        graph: nx.MultiDiGraph,
        node_ids: set[str],
        *,
        edge_types: set[str] | None,
    ) -> list[dict[str, Any]]:
        edges: list[dict[str, Any]] = []
        for source, target, _, data in graph.edges(keys=True, data=True):
            if source not in node_ids or target not in node_ids:
                continue
            if edge_types is not None and data.get("type") not in edge_types:
                continue
            edges.append(
                {
                    "source_id": source,
                    "target_id": target,
                    **dict(data),
                }
            )
        return edges

    def _path_edges(
        self,
        graph: nx.MultiDiGraph,
        path: list[str],
    ) -> list[dict[str, Any]]:
        edges: list[dict[str, Any]] = []
        for source, target in zip(path, path[1:]):
            edge_data = graph.get_edge_data(source, target) or {}
            first_edge = next(iter(edge_data.values()), {})
            edges.append(
                {
                    "source_id": source,
                    "target_id": target,
                    **dict(first_edge),
                }
            )
        return edges

    def _nodes_payload(
        self,
        graph: nx.MultiDiGraph,
        node_ids: set[str],
    ) -> list[dict[str, Any]]:
        return [
            dict(graph.nodes[node_id])
            for node_id in sorted(node_ids)
            if node_id in graph
        ]

    def _node_result(
        self,
        graph: nx.MultiDiGraph,
        node_id: str,
        *,
        result_type: str,
        score: float,
        extra_payload: dict[str, Any] | None = None,
    ) -> RetrievalResult:
        node = dict(graph.nodes[node_id])
        payload = {**node, **(extra_payload or {})}
        symbol = node.get("qualified_name") or node.get("name") or node_id
        return RetrievalResult(
            id=node_id,
            score=score,
            payload=payload,
            result_type=result_type,
            file_path=node.get("file_path"),
            start_line=node.get("start_line"),
            end_line=node.get("end_line"),
            symbol=str(symbol),
            symbol_type=node.get("type") or node.get("label"),
            text=node.get("signature")
            or node.get("qualified_name")
            or node.get("name")
            or "",
        )

    def _normalize_node(self, value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return dict(value)
        return dict(value.items())

    def _normalize_edge(self, value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return dict(value)
        data = dict(value.items())
        if "type" not in data and hasattr(value, "type"):
            data["type"] = value.type
        return data
