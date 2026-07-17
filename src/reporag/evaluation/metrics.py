"""Information retrieval metrics for repository retrieval evaluation."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RetrievalMetrics:
    """Metric bundle for one evaluated query."""

    context_recall_at_k: float
    precision_at_k: float
    mrr: float
    ndcg_at_k: float
    relevant_found: int
    retrieved_count: int
    relevant_count: int


def context_recall_at_k(
    retrieved: list[Any],
    relevant_chunks: list[str] | dict[str, float],
    *,
    k: int,
) -> float:
    """Return fraction of relevant chunks found in the top-k results."""

    relevant = relevance_map(relevant_chunks)
    if not relevant:
        return 0.0
    hits = _hit_ids(retrieved, relevant, k=k)
    return len(hits) / len(relevant)


def precision_at_k(
    retrieved: list[Any],
    relevant_chunks: list[str] | dict[str, float],
    *,
    k: int,
) -> float:
    """Return top-k precision against relevant chunk IDs."""

    if k < 1:
        raise ValueError("k must be at least 1")
    relevant = relevance_map(relevant_chunks)
    top_results = retrieved[:k]
    if not top_results:
        return 0.0
    hits = _hit_ids(top_results, relevant, k=k)
    return len(hits) / min(k, len(top_results))


def mean_reciprocal_rank(
    retrieved: list[Any],
    relevant_chunks: list[str] | dict[str, float],
) -> float:
    """Return reciprocal rank for the first relevant result."""

    relevant = relevance_map(relevant_chunks)
    for rank, item in enumerate(retrieved, start=1):
        if result_id(item) in relevant:
            return 1.0 / rank
    return 0.0


def ndcg_at_k(
    retrieved: list[Any],
    relevant_chunks: list[str] | dict[str, float],
    *,
    k: int,
) -> float:
    """Return normalized discounted cumulative gain at k."""

    if k < 1:
        raise ValueError("k must be at least 1")
    relevant = relevance_map(relevant_chunks)
    if not relevant:
        return 0.0

    dcg = 0.0
    for rank, item in enumerate(retrieved[:k], start=1):
        gain = relevant.get(result_id(item), 0.0)
        dcg += _discounted_gain(gain, rank)

    ideal_gains = sorted(relevant.values(), reverse=True)[:k]
    ideal_dcg = sum(
        _discounted_gain(gain, rank) for rank, gain in enumerate(ideal_gains, start=1)
    )
    if ideal_dcg == 0:
        return 0.0
    return dcg / ideal_dcg


def evaluate_retrieval(
    retrieved: list[Any],
    relevant_chunks: list[str] | dict[str, float],
    *,
    k: int,
) -> RetrievalMetrics:
    """Compute all supported metrics for one query."""

    relevant = relevance_map(relevant_chunks)
    hits = _hit_ids(retrieved, relevant, k=k)
    return RetrievalMetrics(
        context_recall_at_k=context_recall_at_k(
            retrieved,
            relevant,
            k=k,
        ),
        precision_at_k=precision_at_k(retrieved, relevant, k=k),
        mrr=mean_reciprocal_rank(retrieved, relevant),
        ndcg_at_k=ndcg_at_k(retrieved, relevant, k=k),
        relevant_found=len(hits),
        retrieved_count=min(k, len(retrieved)),
        relevant_count=len(relevant),
    )


def relevance_map(relevant_chunks: list[str] | dict[str, float]) -> dict[str, float]:
    """Normalize binary or graded relevance labels into a score map."""

    if isinstance(relevant_chunks, dict):
        return {
            str(chunk_id): float(score)
            for chunk_id, score in relevant_chunks.items()
            if float(score) > 0
        }
    return {str(chunk_id): 1.0 for chunk_id in relevant_chunks}


def result_id(item: Any) -> str:
    """Extract a stable chunk ID from dataclass, object, or dict results."""

    item_id = getattr(item, "id", None)
    if item_id is not None:
        return str(item_id)

    if not isinstance(item, dict):
        raise TypeError("retrieval result must expose an id or be a dict")

    if item.get("id") is not None:
        return str(item["id"])
    payload = item.get("payload", {})
    if isinstance(payload, dict) and payload.get("id") is not None:
        return str(payload["id"])
    raise KeyError("retrieval result dict must include id or payload.id")


def _hit_ids(retrieved: list[Any], relevant: dict[str, float], *, k: int) -> set[str]:
    if k < 1:
        raise ValueError("k must be at least 1")
    return {result_id(item) for item in retrieved[:k] if result_id(item) in relevant}


def _discounted_gain(gain: float, rank: int) -> float:
    return gain / math.log2(rank + 1)
