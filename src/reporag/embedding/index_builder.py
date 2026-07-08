"""Hybrid index builder for Qdrant vectors and BM25 sparse retrieval."""

from __future__ import annotations

import math
import re
import uuid
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from src.reporag.embedding.code_embedder import CodeEmbedding
from src.reporag.embedding.doc_embedder import DocEmbedding

IndexContentType = Literal["code", "doc"]


class VectorStore(Protocol):
    """Vector store operations needed by HybridIndexBuilder."""

    def ensure_collection(self, collection_name: str, vector_size: int) -> None:
        """Create the vector collection and payload indexes when needed."""

    def upsert(self, collection_name: str, documents: list["IndexDocument"]) -> None:
        """Upsert dense vectors and payload metadata."""

    def delete(self, collection_name: str, document_ids: list[str]) -> None:
        """Delete documents from the vector collection."""


@dataclass(frozen=True)
class IndexDocument:
    """One dense/sparse indexable embedding with payload metadata."""

    id: str
    text: str
    vector: list[float]
    content_type: IndexContentType
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def payload(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "text": self.text,
            "content_type": self.content_type,
            **self.metadata,
        }


@dataclass(frozen=True)
class BM25Hit:
    """Sparse retrieval hit."""

    document_id: str
    score: float
    metadata: dict[str, Any]


class CodeAwareTokenizer:
    """Tokenizer that understands snake_case and camelCase code identifiers."""

    _token_pattern = re.compile(r"[A-Za-z][A-Za-z0-9_]*|\d+")
    _camel_boundary = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")

    def tokenize(self, text: str) -> list[str]:
        tokens: list[str] = []
        for raw_token in self._token_pattern.findall(text):
            for snake_part in raw_token.split("_"):
                if not snake_part:
                    continue
                parts = self._camel_boundary.sub(" ", snake_part).split()
                tokens.extend(part.lower() for part in parts if part)
        return tokens


class BM25Index:
    """Small in-memory BM25 index with incremental add/update/delete support."""

    def __init__(
        self,
        *,
        tokenizer: CodeAwareTokenizer | None = None,
        k1: float = 1.5,
        b: float = 0.75,
    ) -> None:
        self.tokenizer = tokenizer or CodeAwareTokenizer()
        self.k1 = k1
        self.b = b
        self._term_frequencies: dict[str, Counter[str]] = {}
        self._document_frequencies: Counter[str] = Counter()
        self._document_lengths: dict[str, int] = {}
        self._metadata: dict[str, dict[str, Any]] = {}

    @property
    def document_count(self) -> int:
        return len(self._term_frequencies)

    @property
    def average_document_length(self) -> float:
        if not self._document_lengths:
            return 0.0
        return sum(self._document_lengths.values()) / len(self._document_lengths)

    def add_or_update(self, documents: Iterable[IndexDocument]) -> None:
        for document in documents:
            self.delete([document.id])
            tokens = self.tokenizer.tokenize(document.text)
            frequencies = Counter(tokens)
            self._term_frequencies[document.id] = frequencies
            self._document_lengths[document.id] = len(tokens)
            self._metadata[document.id] = document.payload
            self._document_frequencies.update(frequencies.keys())

    def delete(self, document_ids: Iterable[str]) -> None:
        for document_id in document_ids:
            frequencies = self._term_frequencies.pop(document_id, None)
            if frequencies is None:
                continue
            for token in frequencies:
                self._document_frequencies[token] -= 1
                if self._document_frequencies[token] <= 0:
                    del self._document_frequencies[token]
            self._document_lengths.pop(document_id, None)
            self._metadata.pop(document_id, None)

    def search(self, query: str, *, limit: int = 10) -> list[BM25Hit]:
        query_tokens = self.tokenizer.tokenize(query)
        if not query_tokens or self.document_count == 0:
            return []

        scores: defaultdict[str, float] = defaultdict(float)
        average_length = self.average_document_length or 1.0

        for token in query_tokens:
            document_frequency = self._document_frequencies.get(token, 0)
            if document_frequency == 0:
                continue
            idf = math.log(
                1
                + (self.document_count - document_frequency + 0.5)
                / (document_frequency + 0.5)
            )
            for document_id, frequencies in self._term_frequencies.items():
                term_frequency = frequencies.get(token, 0)
                if term_frequency == 0:
                    continue
                document_length = self._document_lengths[document_id]
                denominator = term_frequency + self.k1 * (
                    1 - self.b + self.b * document_length / average_length
                )
                scores[document_id] += (
                    idf * term_frequency * (self.k1 + 1) / denominator
                )

        ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        return [
            BM25Hit(
                document_id=document_id,
                score=score,
                metadata=self._metadata[document_id],
            )
            for document_id, score in ranked[:limit]
        ]


class QdrantVectorStore:
    """Qdrant vector store wrapper with collection schema and payload indexes."""

    payload_schema: dict[str, str] = {
        "id": "keyword",
        "content_type": "keyword",
        "source_path": "keyword",
        "symbol_id": "keyword",
        "parent_symbol_id": "keyword",
        "model_name": "keyword",
    }

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
                "Install qdrant-client to use QdrantVectorStore"
            ) from exc

        self.client = QdrantClient(url=url)

    def ensure_collection(self, collection_name: str, vector_size: int) -> None:
        try:
            from qdrant_client.http.models import Distance, VectorParams
        except ImportError:
            vectors_config = {"size": vector_size, "distance": "Cosine"}
        else:
            vectors_config = VectorParams(size=vector_size, distance=Distance.COSINE)

        collection_names = {
            collection.name for collection in self.client.get_collections().collections
        }
        if collection_name not in collection_names:
            self.client.create_collection(
                collection_name=collection_name,
                vectors_config=vectors_config,
            )

        for field_name, field_schema in self.payload_schema.items():
            self.client.create_payload_index(
                collection_name=collection_name,
                field_name=field_name,
                field_schema=field_schema,
            )

    def upsert(self, collection_name: str, documents: list[IndexDocument]) -> None:
        if not documents:
            return

        try:
            from qdrant_client.http.models import PointStruct
        except ImportError as exc:
            raise RuntimeError(
                "Install qdrant-client to use QdrantVectorStore"
            ) from exc

        points = [
            PointStruct(
                id=self._point_id(document.id),
                vector=document.vector,
                payload=document.payload,
            )
            for document in documents
        ]
        self.client.upsert(collection_name=collection_name, points=points)

    def delete(self, collection_name: str, document_ids: list[str]) -> None:
        if not document_ids:
            return
        try:
            from qdrant_client.http.models import PointIdsList
        except ImportError as exc:
            raise RuntimeError(
                "Install qdrant-client to use QdrantVectorStore"
            ) from exc

        self.client.delete(
            collection_name=collection_name,
            points_selector=PointIdsList(
                points=[self._point_id(document_id) for document_id in document_ids]
            ),
        )

    def _point_id(self, document_id: str) -> str:
        return str(uuid.uuid5(uuid.NAMESPACE_URL, document_id))


class HybridIndexBuilder:
    """Build and update Qdrant vector and BM25 sparse indexes together."""

    def __init__(
        self,
        *,
        collection_name: str = "reporag_embeddings",
        vector_store: VectorStore | None = None,
        bm25_index: BM25Index | None = None,
    ) -> None:
        self.collection_name = collection_name
        self.vector_store = vector_store or QdrantVectorStore()
        self.bm25_index = bm25_index or BM25Index()
        self.vector_size: int | None = None

    def build(self, documents: list[IndexDocument]) -> None:
        """Create collection schema and index all documents from scratch."""

        self.upsert(documents)

    def upsert(self, documents: list[IndexDocument]) -> None:
        """Incrementally upsert vector points and sparse BM25 documents."""

        if not documents:
            return

        vector_size = self._validate_vector_sizes(documents)
        self.vector_size = self.vector_size or vector_size
        self.vector_store.ensure_collection(self.collection_name, self.vector_size)
        self.vector_store.upsert(self.collection_name, documents)
        self.bm25_index.add_or_update(documents)

    def delete(self, document_ids: list[str]) -> None:
        """Incrementally remove documents from both indexes."""

        self.vector_store.delete(self.collection_name, document_ids)
        self.bm25_index.delete(document_ids)

    def upsert_code_embeddings(
        self,
        embeddings: list[CodeEmbedding],
        *,
        metadata_by_id: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        documents = [
            self.from_code_embedding(embedding, metadata_by_id=metadata_by_id)
            for embedding in embeddings
        ]
        self.upsert(documents)

    def upsert_doc_embeddings(
        self,
        embeddings: list[DocEmbedding],
        *,
        metadata_by_id: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        documents = [
            self.from_doc_embedding(embedding, metadata_by_id=metadata_by_id)
            for embedding in embeddings
        ]
        self.upsert(documents)

    @staticmethod
    def from_code_embedding(
        embedding: CodeEmbedding,
        *,
        metadata_by_id: dict[str, dict[str, Any]] | None = None,
    ) -> IndexDocument:
        metadata = dict((metadata_by_id or {}).get(embedding.cache_key, {}))
        metadata.update(
            {
                "model_name": embedding.model_name,
                "cache_key": embedding.cache_key,
            }
        )
        return IndexDocument(
            id=embedding.cache_key,
            text=embedding.text,
            vector=embedding.vector,
            content_type="code",
            metadata=metadata,
        )

    @staticmethod
    def from_doc_embedding(
        embedding: DocEmbedding,
        *,
        metadata_by_id: dict[str, dict[str, Any]] | None = None,
    ) -> IndexDocument:
        metadata = dict((metadata_by_id or {}).get(embedding.cache_key, {}))
        metadata.update(
            {
                "model_name": embedding.model_name,
                "cache_key": embedding.cache_key,
                "parent_symbol_id": embedding.parent_symbol_id,
                "source_type": embedding.source_type,
                "source_path": embedding.source_path,
                "start_line": embedding.start_line,
                "end_line": embedding.end_line,
            }
        )
        return IndexDocument(
            id=embedding.cache_key,
            text=embedding.text,
            vector=embedding.vector,
            content_type="doc",
            metadata=metadata,
        )

    def _validate_vector_sizes(self, documents: list[IndexDocument]) -> int:
        vector_size = len(documents[0].vector)
        if vector_size == 0:
            raise ValueError("Index documents must include non-empty vectors")
        for document in documents:
            if len(document.vector) != vector_size:
                raise ValueError(
                    "All vectors in one collection must use the same dimension"
                )
        if self.vector_size is not None and vector_size != self.vector_size:
            raise ValueError("Vector dimension does not match existing collection")
        return vector_size
