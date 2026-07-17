"""Tests for retrieval evaluation metrics and batch runner."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.reporag.evaluation.metrics import (
    context_recall_at_k,
    evaluate_retrieval,
    mean_reciprocal_rank,
    ndcg_at_k,
    precision_at_k,
)
from src.reporag.evaluation.retrieval_eval import (
    RetrievalEvaluator,
    load_eval_dataset,
)


def test_ir_metrics_are_computed_correctly() -> None:
    retrieved = [
        {"id": "chunk-a", "score": 0.9},
        {"id": "chunk-b", "score": 0.8},
        {"id": "chunk-c", "score": 0.7},
    ]
    relevant = ["chunk-b", "chunk-d"]

    assert context_recall_at_k(retrieved, relevant, k=3) == 0.5
    assert precision_at_k(retrieved, relevant, k=2) == 0.5
    assert mean_reciprocal_rank(retrieved, relevant) == 0.5
    assert ndcg_at_k(retrieved, relevant, k=3) == pytest.approx(0.38685, rel=1e-4)


def test_evaluate_retrieval_returns_metric_bundle() -> None:
    metrics = evaluate_retrieval(
        [
            {"id": "first", "score": 0.9},
            {"id": "second", "score": 0.7},
        ],
        {"second": 2.0, "missing": 1.0},
        k=2,
    )

    assert metrics.context_recall_at_k == 0.5
    assert metrics.precision_at_k == 0.5
    assert metrics.mrr == 0.5
    assert metrics.ndcg_at_k > 0
    assert metrics.relevant_found == 1
    assert metrics.relevant_count == 2


def test_retrieval_evaluator_loads_dataset_and_aggregates(tmp_path: Path) -> None:
    dataset_path = tmp_path / "eval.json"
    dataset_path.write_text(
        json.dumps(
            {
                "queries": [
                    {
                        "query": "find auth",
                        "relevant_chunks": ["auth.py:login"],
                    },
                    {
                        "query": "find graph",
                        "relevant_chunks": ["graph.py:build"],
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    evaluator = RetrievalEvaluator.from_json(dataset_path, k=2)

    def strategy(query: str, top_k: int) -> list[dict[str, object]]:
        if "auth" in query:
            return [{"id": "auth.py:login", "score": 1.0}][:top_k]
        return [
            {"id": "other.py:helper", "score": 0.8},
            {"id": "graph.py:build", "score": 0.7},
        ][:top_k]

    report = evaluator.evaluate(strategy, strategy_name="hybrid")

    assert report.strategy_name == "hybrid"
    assert report.aggregate.query_count == 2
    assert report.aggregate.context_recall_at_k == 1.0
    assert report.aggregate.precision_at_k == pytest.approx(0.75)
    assert report.aggregate.mrr == pytest.approx(0.75)
    assert report.to_dict()["queries"][0]["retrieved_ids"] == ["auth.py:login"]


def test_comparison_mode_reports_metric_deltas() -> None:
    dataset = load_eval_dataset("examples/eval_dataset.json")[:2]
    evaluator = RetrievalEvaluator(dataset, k=2)

    def baseline(query: str, top_k: int) -> list[dict[str, object]]:
        return [{"id": "unrelated", "score": 0.1}][:top_k]

    def improved(query: str, top_k: int) -> list[dict[str, object]]:
        return [
            {"id": dataset[0].relevant_chunks[0], "score": 1.0},
            {"id": dataset[1].relevant_chunks[0], "score": 0.9},
        ][:top_k]

    comparison = evaluator.compare(
        {"baseline": baseline, "improved": improved},
        baseline="baseline",
    )

    assert comparison.baseline == "baseline"
    assert comparison.deltas["improved"]["context_recall_at_k"] > 0
    assert comparison.deltas["improved"]["mrr"] > 0
    assert "baseline" in comparison.to_dict()["reports"]


def test_eval_dataset_has_twenty_or_more_query_pairs() -> None:
    dataset = load_eval_dataset("examples/eval_dataset.json")

    assert len(dataset) >= 20
    assert all(item.query for item in dataset)
    assert all(item.relevant_chunks for item in dataset)
