"""Vector semantic search over code and documentation embeddings."""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any, Protocol

from src.reporag.embedding.index_builder import IndexContentType, IndexDocument


class QueryEmbedder(Protocol):
    """Minimal query embedding interface used by VectorSearcher."""

    def embed(self, text: str) -> list[float]:
        """Return a dense vector for query text."""


class VectorSearchBackend(Protocol):
    """Backend interface for vector search stores."""

    def search(
        self,
        collection_name: str,
        query_vector: list[float],
        *,
        limit: int,
        filters: "VectorSearchFilters | None" = None,
    ) -> list["VectorSearchResult"]:
        """Return vector search results for one collection."""


@dataclass(frozen=True)
class VectorSearchFilters:
    """Optional metadata filters for semantic search."""

    language: str | None = None
    file_path: str | None = None
    symbol_type: str | None = None
    content_type: IndexContentType | None = None

    def matches(self, payload: dict[str, Any]) -> bool:
        if self.language is not None and payload.get("language") != self.language:
            return False
        if self.file_path is not None and payload.get("source_path") != self.file_path:
            return False
        if (
            self.symbol_type is not None
            and payload.get("symbol_type") != self.symbol_type
        ):
            return False
        if (
            self.content_type is not None
            and payload.get("content_type") != self.content_type
        ):
            return False
        return True

    def for_content_type(self, content_type: IndexContentType) -> "VectorSearchFilters":
        return VectorSearchFilters(
            language=self.language,
            file_path=self.file_path,
            symbol_type=self.symbol_type,
            content_type=content_type,
        )


@dataclass(frozen=True)
class VectorSearchResult:
    """Ranked vector search result with normalized payload fields."""

    id: str
    score: float
    payload: dict[str, Any]
    collection_name: str
    content_type: IndexContentType
    file_path: str | None = None
    start_line: int | None = None
    end_line: int | None = None
    symbol: str | None = None
    symbol_type: str | None = None
    chunk_text: str = ""

    @classmethod
    def from_payload(
        cls,
        *,
        id: str,
        score: float,
        payload: dict[str, Any],
        collection_name: str,
    ) -> "VectorSearchResult":
        content_type = payload.get("content_type", "code")
        if content_type not in {"code", "doc"}:
            content_type = "code"
        symbol = payload.get("symbol") or payload.get("symbol_id")
        return cls(
            id=str(payload.get("id") or id),
            score=score,
            payload=dict(payload),
            collection_name=collection_name,
            content_type=content_type,
            file_path=payload.get("source_path") or payload.get("file_path"),
            start_line=payload.get("start_line"),
            end_line=payload.get("end_line"),
            symbol=symbol,
            symbol_type=payload.get("symbol_type"),
            chunk_text=payload.get("text") or payload.get("chunk_text") or "",
        )


class InMemoryVectorSearchBackend:
    """Fast local vector backend for tests and small offline indexes."""

    def __init__(self) -> None:
        self._collections: dict[str, dict[str, IndexDocument]] = {}

    def add_documents(
        self,
        collection_name: str,
        documents: list[IndexDocument],
    ) -> None:
        collection = self._collections.setdefault(collection_name, {})
        for document in documents:
            collection[document.id] = document

    def search(
        self,
        collection_name: str,
        query_vector: list[float],
        *,
        limit: int,
        filters: VectorSearchFilters | None = None,
    ) -> list[VectorSearchResult]:
        if limit < 1:
            return []

        results: list[VectorSearchResult] = []
        for document in self._collections.get(collection_name, {}).values():
            payload = document.payload
            if filters is not None and not filters.matches(payload):
                continue
            score = cosine_similarity(query_vector, document.vector)
            results.append(
                VectorSearchResult.from_payload(
                    id=document.id,
                    score=score,
                    payload=payload,
                    collection_name=collection_name,
                )
            )

        return sorted(results, key=lambda result: result.score, reverse=True)[:limit]


class QdrantVectorSearchBackend:
    """Qdrant-backed vector search."""

    def __init__(
        self,
        *,
        url: str = "http://localhost:6333",
        client: Any | None = None,
    ) -> None:
        if client is not None:
            self.client = client
            return

        try:
            from qdrant_client import QdrantClient
        except ImportError as exc:
            raise RuntimeError(
                "Install qdrant-client to use QdrantVectorSearchBackend"
            ) from exc

        self.client = QdrantClient(url=url)

    def search(
        self,
        collection_name: str,
        query_vector: list[float],
        *,
        limit: int,
        filters: VectorSearchFilters | None = None,
    ) -> list[VectorSearchResult]:
        if limit < 1:
            return []

        query_filter = self._build_filter(filters)
        raw_results = self.client.search(
            collection_name=collection_name,
            query_vector=query_vector,
            limit=limit,
            query_filter=query_filter,
            with_payload=True,
        )
        return [
            VectorSearchResult.from_payload(
                id=str(result.id),
                score=float(result.score),
                payload=result.payload or {},
                collection_name=collection_name,
            )
            for result in raw_results
        ]

    def _build_filter(self, filters: VectorSearchFilters | None) -> Any | None:
        if filters is None:
            return None

        conditions: list[Any] = []
        for field_name, value in {
            "language": filters.language,
            "source_path": filters.file_path,
            "symbol_type": filters.symbol_type,
            "content_type": filters.content_type,
        }.items():
            if value is None:
                continue
            conditions.append(self._field_condition(field_name, value))

        if not conditions:
            return None

        try:
            from qdrant_client.http.models import Filter
        except ImportError as exc:
            raise RuntimeError(
                "Install qdrant-client to use QdrantVectorSearchBackend"
            ) from exc

        return Filter(must=conditions)

    def _field_condition(self, field_name: str, value: str) -> Any:
        try:
            from qdrant_client.http.models import FieldCondition, MatchValue
        except ImportError as exc:
            raise RuntimeError(
                "Install qdrant-client to use QdrantVectorSearchBackend"
            ) from exc

        return FieldCondition(key=field_name, match=MatchValue(value=value))


@dataclass(frozen=True)
class VectorSearchResponse:
    """Search response with latency metadata."""

    results: list[VectorSearchResult]
    elapsed_ms: float


@dataclass
class VectorSearcher:
    """Embed queries, search code/doc collections separately, and merge results."""

    query_embedder: QueryEmbedder
    backend: VectorSearchBackend = field(default_factory=QdrantVectorSearchBackend)
    code_collection_name: str = "reporag_code_embeddings"
    doc_collection_name: str = "reporag_doc_embeddings"

    def search(
        self,
        query: str,
        *,
        top_k: int = 20,
        filters: VectorSearchFilters | None = None,
        search_code: bool = True,
        search_docs: bool = True,
    ) -> VectorSearchResponse:
        """Return top-k semantic matches ranked by cosine/vector score."""

        if top_k < 1:
            raise ValueError("top_k must be at least 1")
        if not search_code and not search_docs:
            return VectorSearchResponse(results=[], elapsed_ms=0.0)

        started = time.perf_counter()
        query_vector = self.query_embedder.embed(query)
        collection_results: list[VectorSearchResult] = []

        if search_code:
            collection_results.extend(
                self.backend.search(
                    self.code_collection_name,
                    query_vector,
                    limit=top_k,
                    filters=self._typed_filters(filters, "code"),
                )
            )
        if search_docs:
            collection_results.extend(
                self.backend.search(
                    self.doc_collection_name,
                    query_vector,
                    limit=top_k,
                    filters=self._typed_filters(filters, "doc"),
                )
            )

        ranked = sorted(
            collection_results,
            key=lambda result: result.score,
            reverse=True,
        )[:top_k]
        elapsed_ms = (time.perf_counter() - started) * 1000
        return VectorSearchResponse(results=ranked, elapsed_ms=elapsed_ms)

    def _typed_filters(
        self,
        filters: VectorSearchFilters | None,
        content_type: IndexContentType,
    ) -> VectorSearchFilters:
        if filters is None:
            return VectorSearchFilters(content_type=content_type)
        if filters.content_type is not None and filters.content_type != content_type:
            return filters
        return filters.for_content_type(content_type)


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(left_value * right_value for left_value, right_value in zip(left, right))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)
