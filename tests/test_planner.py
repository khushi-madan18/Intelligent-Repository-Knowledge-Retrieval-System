"""Tests for query classification planner."""

import json

import pytest

from src.reporag.agent.planner import QueryClassification, QueryClassifier


class FakeBackend:
    def __init__(self, response: str) -> None:
        self.response = response
        self.prompts: list[str] = []

    def complete(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.response


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("Where is authenticate_user defined?", "simple-lookup"),
        ("find function parse_repository", "simple-lookup"),
        ("RepositoryStore.save", "simple-lookup"),
        ("What calls create_session?", "simple-lookup"),
        ("How does login flow from API route to database?", "multi-hop"),
        ("Find the path between validate_token and refresh_session", "multi-hop"),
        ("Trace the call chain for ingest_repository", "multi-hop"),
        ("What dependencies are impacted by changing config?", "multi-hop"),
        ("Explain the authentication architecture", "exploratory"),
        ("Give me an overview of ingestion", "exploratory"),
        ("What should I read first to understand retrieval?", "exploratory"),
        ("Compare indexing and retrieval modules", "exploratory"),
    ],
)
def test_heuristic_classifier_handles_10_plus_queries(
    query: str,
    expected: str,
) -> None:
    result = QueryClassifier().classify(query)

    assert isinstance(result, QueryClassification)
    assert result.category == expected
    assert 0 <= result.confidence <= 1


def test_llm_backend_classification_uses_few_shot_prompt() -> None:
    backend = FakeBackend(
        json.dumps(
            {
                "category": "exploratory",
                "confidence": 0.91,
                "reason": "Open-ended architecture question.",
            }
        )
    )
    classifier = QueryClassifier(backend=backend)

    result = classifier.classify("Explain the API architecture")

    assert result.category == "exploratory"
    assert result.confidence == 0.91
    assert result.reason == "Open-ended architecture question."
    assert "Where is authenticate_user defined?" in backend.prompts[0]
    assert "Return strict JSON" in backend.prompts[0]


def test_low_confidence_falls_back_to_multi_hop() -> None:
    backend = FakeBackend(
        json.dumps(
            {
                "category": "simple-lookup",
                "confidence": 0.2,
                "reason": "Not sure.",
            }
        )
    )
    result = QueryClassifier(backend=backend, confidence_threshold=0.55).classify(
        "maybe auth?"
    )

    assert result.category == "multi-hop"
    assert result.confidence == 0.2
    assert result.raw_category == "simple-lookup"
    assert result.used_fallback is True


def test_invalid_llm_category_falls_back_to_multi_hop() -> None:
    backend = FakeBackend(
        json.dumps(
            {
                "category": "not-a-real-category",
                "confidence": 0.95,
                "reason": "Bad output.",
            }
        )
    )

    result = QueryClassifier(backend=backend).classify("route this")

    assert result.category == "multi-hop"
    assert result.raw_category == "not-a-real-category"
    assert result.used_fallback is True


def test_confidence_is_clamped_to_zero_one() -> None:
    backend = FakeBackend(
        json.dumps(
            {
                "category": "simple-lookup",
                "confidence": 8,
                "reason": "Too high.",
            }
        )
    )

    result = QueryClassifier(backend=backend).classify("Where is main?")

    assert result.category == "simple-lookup"
    assert result.confidence == 1.0


def test_empty_and_unparseable_queries_fallback_to_multi_hop() -> None:
    empty = QueryClassifier().classify(" ")
    malformed = QueryClassifier(backend=FakeBackend("not json")).classify("unknown")

    assert empty.category == "multi-hop"
    assert empty.used_fallback is True
    assert malformed.category == "multi-hop"
    assert malformed.used_fallback is True


def test_invalid_threshold_raises() -> None:
    with pytest.raises(ValueError, match="confidence_threshold"):
        QueryClassifier(confidence_threshold=1.5)
