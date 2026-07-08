"""Reciprocal Rank Fusion for retrieval result lists."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class FusedResult:
    """Unified retrieval result produced by rank fusion and reranking."""

    id: str
    score: float
    payload: dict[str, Any]
    text: str = ""
    source_scores: dict[str, float] = field(default_factory=dict)
    source_ranks: dict[str, int] = field(default_factory=dict)
    source_names: list[str] = field(default_factory=list)


class ReciprocalRankFusion:
    """Fuse multiple ranked lists using Reciprocal Rank Fusion."""

    def __init__(self, *, k: int = 60) -> None:
        if k < 1:
            raise ValueError("RRF constant k must be at least 1")
        self.k = k

    def fuse(
        self,
        ranked_lists: list[list[Any]],
        *,
        source_names: list[str] | None = None,
        top_k: int = 20,
    ) -> list[FusedResult]:
        """Fuse 2-3 or more ranked lists into a single top-k ranking."""

        if top_k < 1:
            raise ValueError("top_k must be at least 1")
        if source_names is not None and len(source_names) != len(ranked_lists):
            raise ValueError("source_names must match ranked_lists length")

        names = source_names or [
            f"source_{index + 1}" for index in range(len(ranked_lists))
        ]
        by_id: dict[str, FusedResult] = {}

        for source_index, ranked_list in enumerate(ranked_lists):
            source_name = names[source_index]
            for rank, item in enumerate(ranked_list, start=1):
                item_id = result_id(item)
                payload = result_payload(item)
                text = result_text(item)
                contribution = 1.0 / (self.k + rank)
                existing = by_id.get(item_id)

                if existing is None:
                    by_id[item_id] = FusedResult(
                        id=item_id,
                        score=contribution,
                        payload=payload,
                        text=text,
                        source_scores={source_name: result_score(item)},
                        source_ranks={source_name: rank},
                        source_names=[source_name],
                    )
                    continue

                merged_payload = {**existing.payload, **payload}
                by_id[item_id] = FusedResult(
                    id=item_id,
                    score=existing.score + contribution,
                    payload=merged_payload,
                    text=existing.text or text,
                    source_scores={
                        **existing.source_scores,
                        source_name: result_score(item),
                    },
                    source_ranks={**existing.source_ranks, source_name: rank},
                    source_names=[*existing.source_names, source_name],
                )

        return sorted(by_id.values(), key=lambda item: item.score, reverse=True)[:top_k]


def result_id(item: Any) -> str:
    return str(getattr(item, "id", None) or item["id"])


def result_score(item: Any) -> float:
    value = getattr(item, "score", None)
    if value is None:
        value = item.get("score", 0.0)
    return float(value)


def result_payload(item: Any) -> dict[str, Any]:
    payload = getattr(item, "payload", None)
    if payload is None and isinstance(item, dict):
        payload = item.get("payload", {})
    return dict(payload or {})


def result_text(item: Any) -> str:
    for attr_name in ("chunk_text", "text"):
        value = getattr(item, attr_name, None)
        if isinstance(value, str) and value:
            return value
    if isinstance(item, dict):
        for key in ("chunk_text", "text"):
            value = item.get(key)
            if isinstance(value, str) and value:
                return value
        payload = item.get("payload", {})
    else:
        payload = getattr(item, "payload", {})
    if isinstance(payload, dict):
        value = payload.get("text") or payload.get("chunk_text")
        if isinstance(value, str):
            return value
    return ""
