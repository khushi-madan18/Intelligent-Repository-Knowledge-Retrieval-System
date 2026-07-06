"""Neo4j graph store with a NetworkX fallback implementation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

import networkx as nx
from neo4j import GraphDatabase

from reporag.config import settings
from reporag.graph.call_graph import CallGraphEdge
from reporag.graph.dependency_graph import DependencyEdge
from reporag.graph.symbol_table import SymbolRecord, SymbolTable

SUPPORTED_NODE_LABELS = {"Module", "Function", "Class"}
SUPPORTED_EDGE_TYPES = {"CALLS", "IMPORTS", "INHERITS", "CONTAINS"}


@dataclass(frozen=True)
class GraphNode:
    """Graph node payload."""

    node_id: str
    label: str
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class GraphEdge:
    """Directed graph edge payload."""

    source_id: str
    target_id: str
    edge_type: str
    properties: dict[str, Any] = field(default_factory=dict)


class GraphStore(Protocol):
    """Common graph store interface for Neo4j and NetworkX backends."""

    def connect(self) -> None:
        """Connect to the backing store."""

    def close(self) -> None:
        """Close backing resources."""

    def clear(self) -> None:
        """Remove all graph data."""

    def create_node(self, node: GraphNode) -> None:
        """Create or update a node."""

    def create_edge(self, edge: GraphEdge) -> None:
        """Create or update an edge."""

    def bulk_insert_nodes(self, nodes: list[GraphNode]) -> None:
        """Create or update many nodes."""

    def bulk_insert_edges(self, edges: list[GraphEdge]) -> None:
        """Create or update many edges."""

    def query(
        self,
        cypher: str,
        parameters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Run a query and return rows."""


class NetworkXGraphStore:
    """In-memory graph store implementing the same API as Neo4jGraphStore."""

    def __init__(self) -> None:
        self.graph = nx.MultiDiGraph()

    def connect(self) -> None:
        """NetworkX backend does not need an external connection."""

    def close(self) -> None:
        """NetworkX backend does not hold external resources."""

    def clear(self) -> None:
        self.graph.clear()

    def create_node(self, node: GraphNode) -> None:
        self._validate_node(node)
        self.graph.add_node(
            node.node_id,
            id=node.node_id,
            label=node.label,
            **node.properties,
        )

    def create_edge(self, edge: GraphEdge) -> None:
        self._validate_edge(edge)
        self.graph.add_edge(
            edge.source_id,
            edge.target_id,
            key=edge.edge_type,
            type=edge.edge_type,
            **edge.properties,
        )

    def bulk_insert_nodes(self, nodes: list[GraphNode]) -> None:
        for node in nodes:
            self.create_node(node)

    def bulk_insert_edges(self, edges: list[GraphEdge]) -> None:
        for edge in edges:
            self.create_edge(edge)

    def query(
        self,
        cypher: str,
        parameters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Run a small Cypher-like query subset used by local tests."""

        parameters = parameters or {}
        normalized = " ".join(cypher.split())

        if normalized == "MATCH (n) RETURN n":
            return [{"n": data} for _, data in self.graph.nodes(data=True)]

        if normalized == "MATCH (n {id: $id}) RETURN n":
            node_id = parameters["id"]
            if node_id not in self.graph:
                return []
            return [{"n": self.graph.nodes[node_id]}]

        if normalized == "MATCH (a)-[r]->(b) RETURN a, r, b":
            return [
                {
                    "a": self.graph.nodes[source],
                    "r": data,
                    "b": self.graph.nodes[target],
                }
                for source, target, _, data in self.graph.edges(
                    keys=True,
                    data=True,
                )
            ]

        raise NotImplementedError(f"NetworkX query fallback does not support: {cypher}")

    def get_node(self, node_id: str) -> dict[str, Any] | None:
        if node_id not in self.graph:
            return None
        return dict(self.graph.nodes[node_id])

    def outgoing(
        self,
        node_id: str,
        edge_type: str | None = None,
    ) -> list[tuple[str, dict[str, Any]]]:
        edges: list[tuple[str, dict[str, Any]]] = []
        for _, target, _, data in self.graph.out_edges(node_id, keys=True, data=True):
            if edge_type is None or data.get("type") == edge_type:
                edges.append((target, dict(data)))
        return edges

    def shortest_path(self, source_id: str, target_id: str) -> list[str]:
        simple_graph = nx.DiGraph()
        simple_graph.add_nodes_from(self.graph.nodes)
        simple_graph.add_edges_from(
            (source, target) for source, target in self.graph.edges()
        )
        return nx.shortest_path(simple_graph, source_id, target_id)

    def _validate_node(self, node: GraphNode) -> None:
        if node.label not in SUPPORTED_NODE_LABELS:
            raise ValueError(f"Unsupported node label: {node.label}")

    def _validate_edge(self, edge: GraphEdge) -> None:
        if edge.edge_type not in SUPPORTED_EDGE_TYPES:
            raise ValueError(f"Unsupported edge type: {edge.edge_type}")


class Neo4jGraphStore:
    """Neo4j driver wrapper for graph persistence and Cypher querying."""

    def __init__(
        self,
        *,
        uri: str | None = None,
        user: str | None = None,
        password: str | None = None,
        database: str | None = None,
    ) -> None:
        self.uri = uri or settings.neo4j_uri
        self.user = user or settings.neo4j_user
        self.password = (
            password
            if password is not None
            else settings.neo4j_password.get_secret_value()
        )
        self.database = database
        self._driver: Any | None = None

    def connect(self) -> None:
        self._driver = GraphDatabase.driver(
            self.uri,
            auth=(self.user, self.password),
        )

    def close(self) -> None:
        if self._driver is not None:
            self._driver.close()
            self._driver = None

    def clear(self) -> None:
        self.query("MATCH (n) DETACH DELETE n")

    def create_node(self, node: GraphNode) -> None:
        self.bulk_insert_nodes([node])

    def create_edge(self, edge: GraphEdge) -> None:
        self.bulk_insert_edges([edge])

    def bulk_insert_nodes(self, nodes: list[GraphNode]) -> None:
        grouped: dict[str, list[dict[str, Any]]] = {}
        for node in nodes:
            self._validate_node(node)
            grouped.setdefault(node.label, []).append(
                {"id": node.node_id, **node.properties}
            )

        for label, rows in grouped.items():
            self.query(
                f"""
                UNWIND $rows AS row
                MERGE (n:{label} {{id: row.id}})
                SET n += row
                """,
                {"rows": rows},
            )

    def bulk_insert_edges(self, edges: list[GraphEdge]) -> None:
        grouped: dict[str, list[dict[str, Any]]] = {}
        for edge in edges:
            self._validate_edge(edge)
            grouped.setdefault(edge.edge_type, []).append(
                {
                    "source_id": edge.source_id,
                    "target_id": edge.target_id,
                    "properties": edge.properties,
                }
            )

        for edge_type, rows in grouped.items():
            self.query(
                f"""
                UNWIND $rows AS row
                MATCH (source {{id: row.source_id}})
                MATCH (target {{id: row.target_id}})
                MERGE (source)-[r:{edge_type}]->(target)
                SET r += row.properties
                """,
                {"rows": rows},
            )

    def query(
        self,
        cypher: str,
        parameters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        if self._driver is None:
            self.connect()

        assert self._driver is not None
        with self._driver.session(database=self.database) as session:
            result = session.run(cypher, parameters or {})
            return [dict(record) for record in result]

    def _validate_node(self, node: GraphNode) -> None:
        if node.label not in SUPPORTED_NODE_LABELS:
            raise ValueError(f"Unsupported node label: {node.label}")

    def _validate_edge(self, edge: GraphEdge) -> None:
        if edge.edge_type not in SUPPORTED_EDGE_TYPES:
            raise ValueError(f"Unsupported edge type: {edge.edge_type}")


def symbol_record_to_node(record: SymbolRecord) -> GraphNode:
    """Convert a symbol table record into a graph node."""

    label = _label_for_symbol_type(record.type)
    return GraphNode(
        node_id=record.symbol_id,
        label=label,
        properties={
            "name": record.name,
            "qualified_name": record.qualified_name,
            "type": record.type,
            "file_path": record.file_path,
            "module": record.module,
            "start_line": record.start_line,
            "end_line": record.end_line,
            "signature": record.signature,
        },
    )


def module_node(module: str, file_path: str | None = None) -> GraphNode:
    """Create a module graph node."""

    return GraphNode(
        node_id=f"module:{module}",
        label="Module",
        properties={
            "name": module,
            "qualified_name": module,
            "file_path": file_path or "",
        },
    )


def contains_edge(
    module: str,
    record: SymbolRecord,
    *,
    parent_id: str | None = None,
) -> GraphEdge:
    """Create a Module/Class CONTAINS edge for a symbol record."""

    source_id = parent_id if parent_id is not None else f"module:{module}"
    return GraphEdge(
        source_id=source_id,
        target_id=record.symbol_id,
        edge_type="CONTAINS",
        properties={"child": record.qualified_name},
    )


def calls_edge(edge: CallGraphEdge, symbol_table: SymbolTable) -> GraphEdge | None:
    """Convert a call graph edge to a store edge when both sides are registered."""

    caller = _first_by_name(symbol_table, edge.caller, edge.call_site_file)
    callee = _first_by_name(symbol_table, edge.callee, edge.callee_file)
    if caller is None or callee is None:
        return None
    return GraphEdge(
        source_id=caller.symbol_id,
        target_id=callee.symbol_id,
        edge_type="CALLS",
        properties={
            "call_site_file": edge.call_site_file,
            "call_site_line": edge.call_site_line,
            "call_text": edge.call_text,
        },
    )


def imports_edge(edge: DependencyEdge) -> GraphEdge:
    """Convert an import dependency edge to a module IMPORTS edge."""

    return GraphEdge(
        source_id=f"module:{edge.source}",
        target_id=f"module:{edge.target}",
        edge_type="IMPORTS",
        properties={
            "import_type": edge.import_type,
            "imported_names": edge.imported_names,
            "source_file": edge.source_file,
            "target_file": edge.target_file or "",
            "resolved": edge.resolved,
        },
    )


def inherits_edges(record: SymbolRecord, symbol_table: SymbolTable) -> list[GraphEdge]:
    """Create INHERITS edges for a class record's known base classes."""

    edges: list[GraphEdge] = []
    for base in record.bases:
        base_record = _first_by_name(symbol_table, base, file_path=None)
        if base_record is None:
            continue
        edges.append(
            GraphEdge(
                source_id=record.symbol_id,
                target_id=base_record.symbol_id,
                edge_type="INHERITS",
                properties={"base": base},
            )
        )
    return edges


def load_symbol_table(
    store: GraphStore,
    symbol_table: SymbolTable,
) -> None:
    """Bulk load symbol and module nodes with CONTAINS/INHERITS edges."""

    modules = {
        record.module: record.file_path
        for record in symbol_table.records
        if record.type != "import"
    }
    nodes = [module_node(module, file_path) for module, file_path in modules.items()]
    records = [record for record in symbol_table.records if record.type != "import"]
    nodes.extend(symbol_record_to_node(record) for record in records)

    record_by_qualified_name = {record.qualified_name: record for record in records}
    edges = [
        contains_edge(
            record.module,
            record,
            parent_id=(
                record_by_qualified_name[record.parent_symbol].symbol_id
                if record.parent_symbol in record_by_qualified_name
                else None
            ),
        )
        for record in records
    ]
    for record in records:
        if record.type == "class":
            edges.extend(inherits_edges(record, symbol_table))

    store.bulk_insert_nodes(nodes)
    store.bulk_insert_edges(edges)


def _label_for_symbol_type(symbol_type: str) -> str:
    if symbol_type == "class":
        return "Class"
    if symbol_type in {"function", "method"}:
        return "Function"
    return "Module"


def _first_by_name(
    symbol_table: SymbolTable,
    name: str,
    file_path: str | None,
) -> SymbolRecord | None:
    records = symbol_table.lookup_exact(name)
    if not records and "." in name:
        records = symbol_table.lookup_exact(name.rsplit(".", maxsplit=1)[-1])
    if file_path is not None:
        same_file = [record for record in records if record.file_path == file_path]
        if same_file:
            return same_file[0]
    return records[0] if records else None
