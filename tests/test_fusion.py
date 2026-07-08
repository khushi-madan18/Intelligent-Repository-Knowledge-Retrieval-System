"""Tests for Reciprocal Rank Fusion."""

import pytest

from src.reporag.retrieval.fusion import FusedResult, ReciprocalRankFusion
from src.reporag.retrieval.graph_traversal import RetrievalResult
from src.reporag.retrieval.vector_search import VectorSearchResult


def vector_result(result_id: str, score: float, text: str = "") -> VectorSearchResult:
    return VectorSearchResult(
        id=result_id,
        score=score,
        payload={"text": text, "source_path": f"{result_id}.py"},
        collection_name="vector",
        content_type="code",
        chunk_text=text,
    )


def graph_result(result_id: str, score: float) -> RetrievalResult:
    return RetrievalResult(
        id=result_id,
        score=score,
        payload={"graph": True},
        result_type="neighbor",
        text=f"graph {result_id}",
    )


def test_rrf_fuses_three_ranked_lists_correctly() -> None:
    fusion = ReciprocalRankFusion(k=10)

    results = fusion.fuse(
        [
            [vector_result("a", 0.9), vector_result("b", 0.8)],
            [vector_result("b", 3.0), vector_result("c", 2.0)],
            [graph_result("b", 1.0), graph_result("a", 0.5)],
        ],
        source_names=["vector", "bm25", "graph"],
        top_k=3,
    )

    assert [result.id for result in results] == ["b", "a", "c"]
    assert results[0].source_ranks == {"vector": 2, "bm25": 1, "graph": 1}
    assert results[0].source_scores == {"vector": 0.8, "bm25": 3.0, "graph": 1.0}


def test_rrf_handles_items_missing_from_some_lists() -> None:
    fusion = ReciprocalRankFusion(k=60)

    results = fusion.fuse(
        [[vector_result("only-vector", 0.7)], [vector_result("only-bm25", 2.0)]],
        source_names=["vector", "bm25"],
    )

    assert {result.id for result in results} == {"only-vector", "only-bm25"}
    assert results[0].source_names == ["vector"]
    assert results[1].source_names == ["bm25"]


def test_rrf_preserves_payload_and_text_for_reranking() -> None:
    fusion = ReciprocalRankFusion(k=10)

    result = fusion.fuse([[vector_result("a", 0.9, "def authenticate(): pass")]])[0]

    assert isinstance(result, FusedResult)
    assert result.payload["source_path"] == "a.py"
    assert result.text == "def authenticate(): pass"


def test_rrf_validates_configuration() -> None:
    with pytest.raises(ValueError, match="k"):
        ReciprocalRankFusion(k=0)

    with pytest.raises(ValueError, match="source_names"):
        ReciprocalRankFusion().fuse(
            [[vector_result("a", 1.0)]],
            source_names=["one", "two"],
        )
