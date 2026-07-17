"""Batch retrieval evaluation runner with strategy comparison support."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from src.reporag.evaluation.metrics import RetrievalMetrics, evaluate_retrieval

RetrievalStrategy = Callable[[str, int], Any]


@dataclass(frozen=True)
class EvaluationQuery:
    """One query and its known relevant chunk IDs."""

    query: str
    relevant_chunks: list[str] | dict[str, float]
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class QueryEvaluation:
    """Metrics and retrieved IDs for one query."""

    query: str
    metrics: RetrievalMetrics
    retrieved_ids: list[str]
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AggregateMetrics:
    """Mean metrics across an evaluation dataset."""

    context_recall_at_k: float
    precision_at_k: float
    mrr: float
    ndcg_at_k: float
    query_count: int


@dataclass(frozen=True)
class EvaluationReport:
    """Full evaluation output for one retrieval strategy."""

    strategy_name: str
    k: int
    aggregate: AggregateMetrics
    queries: list[QueryEvaluation]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable report."""

        return asdict(self)


@dataclass(frozen=True)
class StrategyComparison:
    """Aggregate metrics and deltas across retrieval strategies."""

    baseline: str
    reports: dict[str, EvaluationReport]
    deltas: dict[str, dict[str, float]]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable comparison report."""

        return {
            "baseline": self.baseline,
            "reports": {
                name: report.to_dict() for name, report in self.reports.items()
            },
            "deltas": self.deltas,
        }


class RetrievalEvaluator:
    """Evaluate retrieval strategies against query-relevance pairs."""

    def __init__(self, dataset: list[EvaluationQuery], *, k: int = 10) -> None:
        if k < 1:
            raise ValueError("k must be at least 1")
        self.dataset = dataset
        self.k = k

    @classmethod
    def from_json(
        cls,
        path: str | Path,
        *,
        k: int = 10,
    ) -> "RetrievalEvaluator":
        """Load an evaluation dataset from a JSON file."""

        return cls(load_eval_dataset(path), k=k)

    def evaluate(
        self,
        strategy: RetrievalStrategy,
        *,
        strategy_name: str = "retrieval",
    ) -> EvaluationReport:
        """Run one strategy over all queries and aggregate metrics."""

        query_reports: list[QueryEvaluation] = []
        for item in self.dataset:
            results = normalize_results(strategy(item.query, self.k))
            metrics = evaluate_retrieval(
                results,
                item.relevant_chunks,
                k=self.k,
            )
            query_reports.append(
                QueryEvaluation(
                    query=item.query,
                    metrics=metrics,
                    retrieved_ids=[result["id"] for result in results[: self.k]],
                    metadata=item.metadata,
                )
            )

        return EvaluationReport(
            strategy_name=strategy_name,
            k=self.k,
            aggregate=aggregate_metrics(query_reports),
            queries=query_reports,
        )

    def compare(
        self,
        strategies: dict[str, RetrievalStrategy],
        *,
        baseline: str | None = None,
    ) -> StrategyComparison:
        """Evaluate multiple strategies and compute aggregate metric deltas."""

        if not strategies:
            raise ValueError("at least one retrieval strategy is required")
        baseline_name = baseline or next(iter(strategies))
        if baseline_name not in strategies:
            raise ValueError("baseline must be one of the provided strategies")

        reports = {
            name: self.evaluate(strategy, strategy_name=name)
            for name, strategy in strategies.items()
        }
        baseline_metrics = reports[baseline_name].aggregate
        deltas = {
            name: metric_delta(report.aggregate, baseline_metrics)
            for name, report in reports.items()
            if name != baseline_name
        }
        return StrategyComparison(
            baseline=baseline_name,
            reports=reports,
            deltas=deltas,
        )


def load_eval_dataset(path: str | Path) -> list[EvaluationQuery]:
    """Load query-relevance pairs from JSON."""

    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    rows = raw["queries"] if isinstance(raw, dict) else raw
    dataset = [
        EvaluationQuery(
            query=str(row["query"]),
            relevant_chunks=row["relevant_chunks"],
            metadata=dict(row.get("metadata", {})),
        )
        for row in rows
    ]
    if not dataset:
        raise ValueError("evaluation dataset must contain at least one query")
    return dataset


def aggregate_metrics(query_reports: list[QueryEvaluation]) -> AggregateMetrics:
    """Average per-query metrics."""

    if not query_reports:
        return AggregateMetrics(
            context_recall_at_k=0.0,
            precision_at_k=0.0,
            mrr=0.0,
            ndcg_at_k=0.0,
            query_count=0,
        )

    count = len(query_reports)
    return AggregateMetrics(
        context_recall_at_k=sum(
            item.metrics.context_recall_at_k for item in query_reports
        )
        / count,
        precision_at_k=sum(item.metrics.precision_at_k for item in query_reports)
        / count,
        mrr=sum(item.metrics.mrr for item in query_reports) / count,
        ndcg_at_k=sum(item.metrics.ndcg_at_k for item in query_reports) / count,
        query_count=count,
    )


def metric_delta(
    candidate: AggregateMetrics,
    baseline: AggregateMetrics,
) -> dict[str, float]:
    """Return candidate-minus-baseline deltas for aggregate metrics."""

    return {
        "context_recall_at_k": candidate.context_recall_at_k
        - baseline.context_recall_at_k,
        "precision_at_k": candidate.precision_at_k - baseline.precision_at_k,
        "mrr": candidate.mrr - baseline.mrr,
        "ndcg_at_k": candidate.ndcg_at_k - baseline.ndcg_at_k,
    }


def normalize_results(raw_results: Any) -> list[dict[str, Any]]:
    """Normalize common retrieval responses into dicts with stable IDs."""

    results = getattr(raw_results, "results", raw_results)
    if results is None:
        return []
    return [_normalize_result(item) for item in results]


def _normalize_result(item: Any) -> dict[str, Any]:
    item_id = getattr(item, "id", None)
    score = getattr(item, "score", 0.0)
    payload = getattr(item, "payload", {})

    if isinstance(item, dict):
        item_id = item.get("id", item_id)
        score = item.get("score", score)
        payload = item.get("payload", payload)

    if item_id is None and isinstance(payload, dict):
        item_id = payload.get("id")
    if item_id is None:
        raise KeyError("retrieval result is missing an id")

    return {
        "id": str(item_id),
        "score": float(score or 0.0),
        "payload": dict(payload or {}),
    }
