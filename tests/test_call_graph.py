from __future__ import annotations

from reporag.graph.call_graph import CallGraphBuilder, CallGraphEdge, CallGraphInput
from reporag.ingestion.parser import ASTParser
from reporag.ingestion.symbol_extractor import SymbolExtractor


def analyze(file_path: str, source: str) -> CallGraphInput:
    parsed = ASTParser().parse(source, language="python")
    symbols = SymbolExtractor().extract(parsed, file_path)
    return CallGraphInput(file_path=file_path, parsed=parsed, symbols=symbols)


def edge_for(edges: list[CallGraphEdge], caller: str, callee: str) -> CallGraphEdge:
    return next(
        edge for edge in edges if edge.caller == caller and edge.callee == callee
    )


def test_builds_direct_function_call_edges() -> None:
    file_input = analyze(
        "app/service.py",
        """def outer(value):
    return helper(value)

def helper(value):
    return value
""",
    )

    edges = CallGraphBuilder().build([file_input])

    assert [(edge.caller, edge.callee, edge.call_site_line) for edge in edges] == [
        ("outer", "helper", 2)
    ]
    assert edges[0].resolved is True
    assert edges[0].callee_file == "app/service.py"
    assert edges[0].callee_line == 4
    assert edges[0].call_text == "helper(value)"


def test_resolves_method_constructor_and_nested_calls() -> None:
    file_input = analyze(
        "app/user.py",
        """def normalize(value):
    return value

class User:
    def build(self):
        return self.save(normalize(User()))

    def save(self, value):
        return value
""",
    )

    edges = CallGraphBuilder().build([file_input])

    assert edge_for(edges, "User.build", "User.save").call_site_line == 6
    assert edge_for(edges, "User.build", "normalize").call_site_line == 6
    assert edge_for(edges, "User.build", "User").call_site_line == 6
    assert all(edge.resolved for edge in edges)


def test_resolves_cross_file_imported_calls() -> None:
    service = analyze(
        "app/service.py",
        """from app.helpers import normalize
import app.factory as factory

def run(value):
    item = normalize(value)
    return factory.create(item)
""",
    )
    helpers = analyze(
        "app/helpers.py",
        """def normalize(value):
    return value
""",
    )
    factory_file = analyze(
        "app/factory.py",
        """def create(value):
    return value
""",
    )

    edges = CallGraphBuilder().build([service, helpers, factory_file])

    normalize_edge = edge_for(edges, "run", "normalize")
    assert normalize_edge.resolved is True
    assert normalize_edge.callee_file == "app/helpers.py"
    assert normalize_edge.call_site_line == 5

    create_edge = edge_for(edges, "run", "create")
    assert create_edge.resolved is True
    assert create_edge.callee_file == "app/factory.py"
    assert create_edge.call_site_line == 6
    assert create_edge.call_text == "factory.create(item)"


def test_resolves_recursive_calls() -> None:
    file_input = analyze(
        "maths.py",
        """def factorial(value):
    if value <= 1:
        return 1
    return value * factorial(value - 1)
""",
    )

    edges = CallGraphBuilder().build([file_input])

    assert [(edge.caller, edge.callee) for edge in edges] == [
        ("factorial", "factorial")
    ]
    assert edges[0].resolved is True
    assert edges[0].callee_file == "maths.py"
    assert edges[0].call_site_line == 4
