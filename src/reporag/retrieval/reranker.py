"""Cross-encoder reranking for fused retrieval candidates."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Protocol

from src.reporag.retrieval.fusion import FusedResult, result_text

DEFAULT_RERANKER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"


class CrossEncoderBackend(Protocol):
    """Cross-encoder scoring backend."""

    model_name: str

    def score(self, pairs: list[tuple[str, str]]) -> list[float]:
        """Score query/document pairs."""


class SentenceTransformersCrossEncoderBackend:
    """sentence-transformers CrossEncoder backend."""

    def __init__(
        self,
        model_name: str = DEFAULT_RERANKER_MODEL,
        *,
        device: str | None = None,
    ) -> None:
        try:
            from sentence_transformers import CrossEncoder
        except ImportError as exc:
            raise RuntimeError(
                "Install sentence-transformers to use the cross-encoder reranker"
            ) from exc

        self.model_name = model_name
        self.model = CrossEncoder(model_name, device=device)

    def score(self, pairs: list[tuple[str, str]]) -> list[float]:
        if not pairs:
            return []
        scores = self.model.predict(pairs, show_progress_bar=False)
        return [float(score) for score in scores]


@dataclass(frozen=True)
class RerankResponse:
    """Reranking response with latency metadata."""

    results: list[FusedResult]
    elapsed_ms: float


class CrossEncoderReranker:
    """Rerank candidates by scoring (query, chunk) pairs."""

    def __init__(
        self,
        *,
        backend: CrossEncoderBackend | None = None,
        model_name: str = DEFAULT_RERANKER_MODEL,
    ) -> None:
        self.backend = backend or SentenceTransformersCrossEncoderBackend(
            model_name=model_name
        )

    def rerank(
        self,
        query: str,
        candidates: list[FusedResult],
        *,
        top_k: int = 20,
    ) -> RerankResponse:
        """Return final top-k candidates ordered by cross-encoder score."""

        if top_k < 1:
            raise ValueError("top_k must be at least 1")

        started = time.perf_counter()
        pairs = [(query, result_text(candidate)) for candidate in candidates]
        scores = self.backend.score(pairs)
        if len(scores) != len(candidates):
            raise ValueError("Cross-encoder backend returned the wrong score count")

        reranked = [
            FusedResult(
                id=candidate.id,
                score=score,
                payload={
                    **candidate.payload,
                    "rrf_score": candidate.score,
                    "rerank_score": score,
                },
                text=candidate.text,
                source_scores=candidate.source_scores,
                source_ranks=candidate.source_ranks,
                source_names=candidate.source_names,
            )
            for candidate, score in zip(candidates, scores, strict=True)
        ]
        ordered = sorted(reranked, key=lambda item: item.score, reverse=True)[:top_k]
        elapsed_ms = (time.perf_counter() - started) * 1000
        return RerankResponse(results=ordered, elapsed_ms=elapsed_ms)
