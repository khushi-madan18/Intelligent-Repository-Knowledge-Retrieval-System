"""BM25 sparse keyword search for code identifiers."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Any

from src.reporag.embedding.index_builder import BM25Hit, BM25Index, CodeAwareTokenizer
from src.reporag.retrieval.vector_search import (
    VectorSearchFilters,
    VectorSearchResponse,
    VectorSearchResult,
)


@dataclass
class BM25Searcher:
    """Search a BM25 index and boost exact function/class name matches."""

    bm25_index: BM25Index
    collection_name: str = "bm25"
    exact_name_boost: float = 5.0

    @property
    def tokenizer(self) -> CodeAwareTokenizer:
        return self.bm25_index.tokenizer

    def search(
        self,
        query: str,
        *,
        top_k: int = 20,
        filters: VectorSearchFilters | None = None,
    ) -> VectorSearchResponse:
        """Return top-k BM25 matches using the same result schema as vector search."""

        if top_k < 1:
            raise ValueError("top_k must be at least 1")

        started = time.perf_counter()
        candidate_limit = max(self.bm25_index.document_count, top_k)
        hits = self.bm25_index.search(query, limit=candidate_limit)
        results = [
            self._to_result(hit, query)
            for hit in hits
            if filters is None or filters.matches(hit.metadata)
        ]
        ranked = sorted(results, key=lambda result: result.score, reverse=True)[:top_k]
        elapsed_ms = (time.perf_counter() - started) * 1000
        return VectorSearchResponse(results=ranked, elapsed_ms=elapsed_ms)

    def tokenize_query(self, query: str) -> list[str]:
        """Expose code-aware query tokenization for callers and tests."""

        return self.tokenizer.tokenize(query)

    def _to_result(self, hit: BM25Hit, query: str) -> VectorSearchResult:
        payload = dict(hit.metadata)
        exact_match = self._is_exact_name_match(query, payload)
        score = hit.score + (self.exact_name_boost if exact_match else 0.0)
        payload["bm25_score"] = hit.score
        payload["exact_name_match"] = exact_match
        return VectorSearchResult.from_payload(
            id=hit.document_id,
            score=score,
            payload=payload,
            collection_name=self.collection_name,
        )

    def _is_exact_name_match(self, query: str, payload: dict[str, Any]) -> bool:
        if payload.get("symbol_type") not in {"function", "class", "method"}:
            return False

        query_name = normalize_identifier(query)
        if not query_name:
            return False

        for candidate in self._candidate_symbol_names(payload):
            candidate_name = normalize_identifier(candidate)
            if query_name == candidate_name:
                return True
        return False

    def _candidate_symbol_names(self, payload: dict[str, Any]) -> list[str]:
        candidates = [
            payload.get("symbol_name"),
            payload.get("name"),
            payload.get("symbol"),
            payload.get("symbol_id"),
        ]
        names: list[str] = []
        for candidate in candidates:
            if not isinstance(candidate, str) or not candidate:
                continue
            names.append(candidate)
            terminal_name = re.split(r"[:.]", candidate)[-1]
            if terminal_name and terminal_name != candidate:
                names.append(terminal_name)
        return names


def normalize_identifier(identifier: str) -> str:
    """Normalize code identifiers for exact name matching."""

    return "".join(token.lower() for token in CodeAwareTokenizer().tokenize(identifier))
