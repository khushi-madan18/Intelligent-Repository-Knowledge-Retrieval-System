"""Tests for query decomposition planner."""

import json

from src.reporag.agent.planner import (
    QueryClassification,
    QueryClassifier,
    QueryDecomposer,
    SubQuery,
)


class FakeBackend:
    def __init__(self, response: str) -> None:
        self.response = response
        self.prompts: list[str] = []

    def complete(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.response


class StaticClassifier(QueryClassifier):
    def __init__(self, classification: QueryClassification) -> None:
        self.classification = classification

    def classify(self, query: str) -> QueryClassification:
        return self.classification


def classification(category: str) -> QueryClassification:
    return QueryClassification(
        query="query",
        category=category,  # type: ignore[arg-type]
        confidence=0.9,
        reason="test",
        raw_category=category,
    )


def test_multihop_query_decomposes_into_ordered_subqueries() -> None:
    decomposer = QueryDecomposer(
        classifier=StaticClassifier(classification("multi-hop"))
    )

    result = decomposer.decompose(
        "How does login flow from API route to database?",
        repo_context="Modules: api.routes.auth, services.auth, db.sessions",
    )

    assert result.needs_decomposition is True
    assert 2 <= len(result.sub_queries) <= 5
    assert [sub_query.id for sub_query in result.sub_queries] == ["q1", "q2", "q3"]
    assert result.sub_queries[1].context_from == ["q1"]
    assert result.sub_queries[2].context_from == ["q1", "q2"]
    assert (
        result.repo_context_used
        == "Modules: api.routes.auth, services.auth, db.sessions"
    )


def test_subqueries_have_dependency_edges() -> None:
    decomposer = QueryDecomposer(
        classifier=StaticClassifier(classification("multi-hop"))
    )

    result = decomposer.decompose("Trace request flow")

    assert [(edge.source, edge.target) for edge in result.dependency_edges] == [
        ("q1", "q2"),
        ("q2", "q3"),
    ]


def test_llm_decomposition_uses_repo_context_for_prompt() -> None:
    backend = FakeBackend(
        json.dumps(
            {
                "needs_decomposition": True,
                "sub_queries": [
                    {
                        "id": "q1",
                        "text": "Find the FastAPI route in api/auth.py",
                        "expected_answer_type": "symbol",
                        "context_from": [],
                    },
                    {
                        "id": "q2",
                        "text": "Trace calls from q1 into services/auth.py",
                        "expected_answer_type": "path",
                        "context_from": ["q1"],
                    },
                ],
                "dependency_edges": [
                    {
                        "source": "q1",
                        "target": "q2",
                        "reason": "The call trace starts from the route.",
                    }
                ],
            }
        )
    )
    decomposer = QueryDecomposer(
        backend=backend,
        classifier=StaticClassifier(classification("multi-hop")),
    )

    result = decomposer.decompose(
        "How does login reach the database?",
        repo_context="Files: api/auth.py, services/auth.py, db/session.py",
    )

    assert "Files: api/auth.py" in backend.prompts[0]
    assert result.sub_queries[0].text == "Find the FastAPI route in api/auth.py"
    assert result.dependency_edges[0].source == "q1"
    assert result.dependency_edges[0].target == "q2"


def test_simple_lookup_does_not_need_decomposition() -> None:
    decomposer = QueryDecomposer(
        classifier=StaticClassifier(classification("simple-lookup"))
    )

    result = decomposer.decompose("Where is authenticate_user defined?")

    assert result.needs_decomposition is False
    assert result.sub_queries == [
        SubQuery(
            id="q1",
            text="Where is authenticate_user defined?",
            expected_answer_type="symbol",
            context_from=[],
        )
    ]
    assert result.dependency_edges == []


def test_exploratory_query_can_skip_multihop_decomposition() -> None:
    decomposer = QueryDecomposer(
        classifier=StaticClassifier(classification("exploratory"))
    )

    result = decomposer.decompose("Explain the authentication architecture")

    assert result.needs_decomposition is False
    assert result.sub_queries[0].expected_answer_type == "explanation"


def test_invalid_llm_decomposition_falls_back_to_heuristic_plan() -> None:
    backend = FakeBackend(
        json.dumps(
            {
                "needs_decomposition": True,
                "sub_queries": [
                    {
                        "id": "q1",
                        "text": "Only one step",
                        "expected_answer_type": "symbol",
                        "context_from": [],
                    }
                ],
                "dependency_edges": [],
            }
        )
    )
    decomposer = QueryDecomposer(
        backend=backend,
        classifier=StaticClassifier(classification("multi-hop")),
    )

    result = decomposer.decompose("Trace the request")

    assert len(result.sub_queries) == 3
    assert result.dependency_edges[0].source == "q1"


def test_state_machine_has_clear_transitions() -> None:
    decomposer = QueryDecomposer(
        classifier=StaticClassifier(classification("multi-hop"))
    )

    result = decomposer.decompose("Trace request flow")

    assert decomposer.state_machine.transitions == [
        "classify",
        "route",
        "decompose",
        "validate",
        "finalize",
    ]
    assert result.transitions == [
        "classify",
        "route",
        "decompose",
        "validate",
        "finalize",
    ]
