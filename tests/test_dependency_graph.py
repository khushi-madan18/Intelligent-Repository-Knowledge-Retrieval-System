from __future__ import annotations

from reporag.graph.dependency_graph import (
    DependencyEdge,
    DependencyGraphBuilder,
    DependencyGraphInput,
)
from reporag.ingestion.parser import ASTParser
from reporag.ingestion.symbol_extractor import SymbolExtractor


def analyze(file_path: str, source: str) -> DependencyGraphInput:
    parsed = ASTParser().parse(source, language="python")
    symbols = SymbolExtractor().extract(parsed, file_path)
    return DependencyGraphInput(file_path=file_path, symbols=symbols)


def edge_for(
    edges: list[DependencyEdge],
    source: str,
    target: str,
) -> DependencyEdge:
    return next(
        edge for edge in edges if edge.source == source and edge.target == target
    )


def test_resolves_absolute_imports_and_from_imports() -> None:
    service = analyze(
        "app/service.py",
        """import os
import app.factory as factory
from app.helpers import normalize, denormalize as denorm
""",
    )
    helpers = analyze("app/helpers.py", "def normalize(value):\n    return value\n")
    factory = analyze("app/factory.py", "def create(value):\n    return value\n")

    graph = DependencyGraphBuilder().build([service, helpers, factory])

    external = edge_for(graph.edges, "app.service", "os")
    assert external.import_type == "import"
    assert external.imported_names == ["os"]
    assert external.resolved is False

    factory_edge = edge_for(graph.edges, "app.service", "app.factory")
    assert factory_edge.resolved is True
    assert factory_edge.target_file == "app/factory.py"
    assert factory_edge.imported_names == ["app.factory"]

    helpers_edge = edge_for(graph.edges, "app.service", "app.helpers")
    assert helpers_edge.resolved is True
    assert helpers_edge.target_file == "app/helpers.py"
    assert helpers_edge.import_type == "from_import"
    assert helpers_edge.imported_names == ["normalize", "denormalize as denorm"]


def test_resolves_relative_imports_to_absolute_modules() -> None:
    service = analyze(
        "app/services/user.py",
        """from .auth import authenticate
from ..models import User
from . import permissions
""",
    )
    auth = analyze("app/services/auth.py", "def authenticate():\n    return True\n")
    models = analyze("app/models.py", "class User:\n    pass\n")
    permissions = analyze("app/services/permissions.py", "ALLOW = True\n")

    graph = DependencyGraphBuilder().build([service, auth, models, permissions])

    auth_edge = edge_for(graph.edges, "app.services.user", "app.services.auth")
    assert auth_edge.resolved is True
    assert auth_edge.imported_names == ["authenticate"]

    models_edge = edge_for(graph.edges, "app.services.user", "app.models")
    assert models_edge.resolved is True
    assert models_edge.imported_names == ["User"]

    package_edge = edge_for(
        graph.edges,
        "app.services.user",
        "app.services.permissions",
    )
    assert package_edge.resolved is True
    assert package_edge.imported_names == ["permissions"]


def test_handles_star_imports_with_warning() -> None:
    consumer = analyze("app/consumer.py", "from app.settings import *\n")
    settings = analyze("app/settings.py", "VALUE = 1\n")

    graph = DependencyGraphBuilder().build([consumer, settings])

    edge = edge_for(graph.edges, "app.consumer", "app.settings")
    assert edge.import_type == "from_import"
    assert edge.imported_names == ["*"]
    assert edge.is_star_import is True
    assert edge.warning == "Star import from app.settings makes dependencies implicit"
    assert edge.resolved is True


def test_detects_circular_import_chains() -> None:
    module_a = analyze("app/a.py", "from app import b\n")
    module_b = analyze("app/b.py", "from app.c import thing\n")
    module_c = analyze("app/c.py", "from app import a\nthing = 1\n")

    graph = DependencyGraphBuilder().build([module_a, module_b, module_c])

    assert [cycle.chain for cycle in graph.circular_imports] == [
        ["app.a", "app.b", "app.c", "app.a"]
    ]
