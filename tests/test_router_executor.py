"""Tests for strategy routing and sub-query execution."""

import pytest

from src.reporag.agent.executor import ExecutionContext, SubQueryExecutor
from src.reporag.agent.planner import (
    QueryClassification,
    QueryDecomposition,
    SubQuery,
    SubQueryDependency,
)
from src.reporag.agent.router import StrategyRouter


def make_decomposition() -> QueryDecomposition:
    classification = QueryClassification(
        query="How does login flow?",
        category="multi-hop",
        confidence=0.9,
    )
    return QueryDecomposition(
        query="How does login flow?",
        needs_decomposition=True,
        classification=classification,
        sub_queries=[
            SubQuery(
                id="q1",
                text="Find function authenticate_user",
                expected_answer_type="symbol",
                context_from=[],
            ),
            SubQuery(
                id="q2",
                text="Trace calls from q1 to database",
                expected_answer_type="path",
                context_from=["q1"],
            ),
            SubQuery(
                id="q3",
                text="Explain login behavior from retrieved context",
                expected_answer_type="explanation",
                context_from=["q1", "q2"],
            ),
        ],
        dependency_edges=[
            SubQueryDependency("q1", "q2"),
            SubQueryDependency("q2", "q3"),
        ],
    )


def test_routes_identifier_lookups_to_bm25() -> None:
    route = StrategyRouter().route(
        SubQuery(
            id="q1",
            text="authenticate_user",
            expected_answer_type="symbol",
            context_from=[],
        )
    )

    assert route.strategy == "bm25"


def test_routes_structural_queries_to_graph() -> None:
    route = StrategyRouter().route(
        SubQuery(
            id="q2",
            text="Trace calls from API route to database",
            expected_answer_type="path",
            context_from=["q1"],
        )
    )

    assert route.strategy == "graph"


def test_routes_semantic_queries_to_vector() -> None:
    route = StrategyRouter().route(
        SubQuery(
            id="q3",
            text="Explain why authentication refreshes sessions",
            expected_answer_type="explanation",
            context_from=[],
        )
    )

    assert route.strategy == "vector"


def test_routes_evidence_queries_to_hybrid() -> None:
    route = StrategyRouter().route(
        SubQuery(
            id="q4",
            text="Collect supporting code and docs",
            expected_answer_type="evidence",
            context_from=["q1", "q2"],
        )
    )

    assert route.strategy == "hybrid"


def test_executor_respects_dependency_order_and_context_forwarding() -> None:
    calls: list[tuple[str, str, dict[str, list[str]]]] = []

    def run_strategy(context: ExecutionContext) -> list[str]:
        calls.append(
            (
                context.sub_query.id,
                context.route.strategy,
                {key: list(value) for key, value in context.dependency_results.items()},
            )
        )
        return [f"result:{context.sub_query.id}"]

    executor = SubQueryExecutor(
        executors={
            "bm25": run_strategy,
            "graph": run_strategy,
            "vector": run_strategy,
        }
    )

    result = executor.execute(make_decomposition())

    assert [step.sub_query.id for step in result.steps] == ["q1", "q2", "q3"]
    assert [step.route.strategy for step in result.steps] == [
        "bm25",
        "graph",
        "vector",
    ]
    assert calls[1][2] == {"q1": ["result:q1"]}
    assert calls[2][2] == {"q1": ["result:q1"], "q2": ["result:q2"]}


def test_hybrid_executor_falls_back_to_available_retrievers() -> None:
    def bm25(context: ExecutionContext) -> list[str]:
        return [f"bm25:{context.sub_query.id}"]

    def vector(context: ExecutionContext) -> list[str]:
        return [f"vector:{context.sub_query.id}"]

    decomposition = QueryDecomposition(
        query="Collect evidence",
        needs_decomposition=True,
        classification=QueryClassification(
            query="Collect evidence",
            category="multi-hop",
            confidence=0.9,
        ),
        sub_queries=[
            SubQuery(
                id="q1",
                text="Collect supporting evidence",
                expected_answer_type="evidence",
                context_from=[],
            )
        ],
        dependency_edges=[],
    )

    result = SubQueryExecutor(executors={"bm25": bm25, "vector": vector}).execute(
        decomposition
    )

    assert result.steps[0].route.strategy == "hybrid"
    assert result.results_by_sub_query["q1"] == ["bm25:q1", "vector:q1"]


def test_executor_detects_dependency_cycles() -> None:
    classification = QueryClassification("cycle", "multi-hop", 0.9)
    decomposition = QueryDecomposition(
        query="cycle",
        needs_decomposition=True,
        classification=classification,
        sub_queries=[
            SubQuery("q1", "first", "symbol", ["q2"]),
            SubQuery("q2", "second", "path", ["q1"]),
        ],
        dependency_edges=[
            SubQueryDependency("q1", "q2"),
            SubQueryDependency("q2", "q1"),
        ],
    )

    with pytest.raises(ValueError, match="cycle"):
        SubQueryExecutor().execute(decomposition)
