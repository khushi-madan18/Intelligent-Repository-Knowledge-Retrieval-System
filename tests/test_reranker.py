"""Tests for cross-encoder reranking."""

import pytest

from src.reporag.retrieval.fusion import FusedResult
from src.reporag.retrieval.reranker import CrossEncoderReranker


class KeywordBackend:
    model_name = "fake-cross-encoder"

    def __init__(self, keyword: str = "correct") -> None:
        self.keyword = keyword
        self.calls: list[list[tuple[str, str]]] = []

    def score(self, pairs: list[tuple[str, str]]) -> list[float]:
        self.calls.append(list(pairs))
        return [
            10.0 if self.keyword in document else float(index)
            for index, (_, document) in enumerate(pairs)
        ]


class ShortScoreBackend(KeywordBackend):
    def score(self, pairs: list[tuple[str, str]]) -> list[float]:
        super().score(pairs)
        return []


class ExactTextBackend(KeywordBackend):
    def score(self, pairs: list[tuple[str, str]]) -> list[float]:
        self.calls.append(list(pairs))
        return [
            100.0 if document == self.keyword else float(index)
            for index, (_, document) in enumerate(pairs)
        ]


def candidate(result_id: str, rrf_score: float, text: str) -> FusedResult:
    return FusedResult(
        id=result_id,
        score=rrf_score,
        payload={"text": text},
        text=text,
        source_scores={"rrf": rrf_score},
        source_ranks={"rrf": 1},
        source_names=["rrf"],
    )


def test_cross_encoder_reranks_and_reorders_candidates() -> None:
    reranker = CrossEncoderReranker(backend=KeywordBackend())
    candidates = [
        candidate("wrong-high-rrf", 1.0, "unrelated helper"),
        candidate("right-low-rrf", 0.1, "correct authentication flow"),
    ]

    response = reranker.rerank("How does auth work?", candidates, top_k=2)

    assert [result.id for result in response.results] == [
        "right-low-rrf",
        "wrong-high-rrf",
    ]
    assert response.results[0].payload["rrf_score"] == 0.1
    assert response.results[0].payload["rerank_score"] == 10.0


def test_reranked_outperforms_rrf_only_for_relevant_candidate() -> None:
    reranker = CrossEncoderReranker(backend=KeywordBackend("save user"))
    candidates = [
        candidate("rrf-first", 0.9, "generic repository helper"),
        candidate("relevant", 0.2, "save user profile to database"),
    ]

    rrf_only_top = candidates[0].id
    reranked_top = reranker.rerank("Where is the user saved?", candidates).results[0].id

    assert rrf_only_top == "rrf-first"
    assert reranked_top == "relevant"


def test_reranking_20_candidates_under_500ms() -> None:
    reranker = CrossEncoderReranker(backend=ExactTextBackend("candidate 19"))
    candidates = [
        candidate(f"id:{index}", 1.0 / (index + 1), f"candidate {index}")
        for index in range(20)
    ]

    response = reranker.rerank("find final candidate", candidates, top_k=20)

    assert len(response.results) == 20
    assert response.results[0].id == "id:19"
    assert response.elapsed_ms < 500


def test_invalid_top_k_and_backend_count_errors() -> None:
    reranker = CrossEncoderReranker(backend=KeywordBackend())

    with pytest.raises(ValueError, match="top_k"):
        reranker.rerank("query", [], top_k=0)

    with pytest.raises(ValueError, match="wrong score count"):
        CrossEncoderReranker(backend=ShortScoreBackend()).rerank(
            "query",
            [candidate("one", 1.0, "text")],
        )
