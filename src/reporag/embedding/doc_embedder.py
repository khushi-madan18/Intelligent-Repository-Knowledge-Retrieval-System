"""Natural-language embedding pipeline for docs, comments, and README text."""

from __future__ import annotations

import hashlib
import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal, Protocol

from src.reporag.embedding.code_embedder import EmbeddingCache

DEFAULT_DOC_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
DEFAULT_DOC_EMBEDDING_DIM = 384

DocSourceType = Literal["docstring", "comment", "readme"]
ProgressCallback = Callable[[int, int], None]


class DocEmbeddingBackend(Protocol):
    """Backend interface used by DocEmbedder."""

    model_name: str
    device: str
    embedding_dim: int

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Return one embedding per natural-language text."""


@dataclass(frozen=True)
class DocEmbeddingInput:
    """Natural-language text tied to an optional repository/code location."""

    text: str
    parent_symbol_id: str
    source_type: DocSourceType = "docstring"
    source_path: str | None = None
    start_line: int | None = None
    end_line: int | None = None


@dataclass(frozen=True)
class DocEmbedding:
    """Embedded natural-language text linked back to a parent symbol."""

    text: str
    vector: list[float]
    parent_symbol_id: str
    source_type: DocSourceType
    model_name: str
    cache_key: str
    source_path: str | None = None
    start_line: int | None = None
    end_line: int | None = None


class SentenceTransformerDocBackend:
    """Sentence-transformers backend for docstring/comment embeddings."""

    def __init__(
        self,
        model_name: str = DEFAULT_DOC_MODEL_NAME,
        *,
        device: str | None = None,
    ) -> None:
        try:
            import torch
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError(
                "Install sentence-transformers to use SentenceTransformerDocBackend"
            ) from exc

        self.model_name = model_name
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.model = SentenceTransformer(model_name, device=self.device)
        model_dim = self.model.get_sentence_embedding_dimension()
        self.embedding_dim = model_dim or DEFAULT_DOC_EMBEDDING_DIM

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        vectors = self.model.encode(
            texts,
            batch_size=len(texts),
            convert_to_numpy=True,
            normalize_embeddings=False,
            show_progress_bar=False,
        )
        return vectors.tolist()


class DocEmbedder:
    """Embed docstrings, comments, and README sections with progress reporting."""

    def __init__(
        self,
        *,
        model_name: str = DEFAULT_DOC_MODEL_NAME,
        batch_size: int = 32,
        backend: DocEmbeddingBackend | None = None,
        cache: EmbeddingCache | None = None,
    ) -> None:
        if batch_size < 1:
            raise ValueError("batch_size must be at least 1")

        self.model_name = model_name
        self.batch_size = batch_size
        self.backend = (
            backend
            if backend is not None
            else SentenceTransformerDocBackend(model_name=model_name)
        )
        self.embedding_dim = self.backend.embedding_dim
        self.cache = cache if cache is not None else EmbeddingCache()

    @property
    def device(self) -> str:
        return self.backend.device

    def embed(
        self,
        text: str,
        *,
        parent_symbol_id: str,
        source_type: DocSourceType = "docstring",
        source_path: str | None = None,
        start_line: int | None = None,
        end_line: int | None = None,
    ) -> DocEmbedding:
        """Embed one natural-language text item."""

        document = DocEmbeddingInput(
            text=text,
            parent_symbol_id=parent_symbol_id,
            source_type=source_type,
            source_path=source_path,
            start_line=start_line,
            end_line=end_line,
        )
        return self.embed_batch([document])[0]

    def embed_batch(
        self,
        documents: list[DocEmbeddingInput],
        *,
        batch_size: int | None = None,
        progress_callback: ProgressCallback | None = None,
    ) -> list[DocEmbedding]:
        """Embed documents in batches and call progress_callback(processed, total)."""

        if not documents:
            if progress_callback is not None:
                progress_callback(0, 0)
            return []

        active_batch_size = batch_size or self.batch_size
        if active_batch_size < 1:
            raise ValueError("batch_size must be at least 1")

        results: list[DocEmbedding | None] = [None] * len(documents)
        total = len(documents)

        for start in range(0, total, active_batch_size):
            batch_documents = documents[start : start + active_batch_size]
            uncached: list[tuple[int, DocEmbeddingInput, str]] = []

            for offset, document in enumerate(batch_documents):
                index = start + offset
                key = self.cache_key(document)
                cached_vector = self.cache.get(key)
                if cached_vector is not None:
                    results[index] = self._make_embedding(document, cached_vector, key)
                    continue
                if not document.text.strip():
                    zero_vector = [0.0] * self.embedding_dim
                    self.cache.set(key, zero_vector)
                    results[index] = self._make_embedding(document, zero_vector, key)
                    continue
                uncached.append((index, document, key))

            if uncached:
                vectors = self.backend.embed_batch([item[1].text for item in uncached])
                if len(vectors) != len(uncached):
                    raise ValueError(
                        "Embedding backend returned the wrong batch length"
                    )

                for (index, document, key), vector in zip(
                    uncached, vectors, strict=True
                ):
                    if len(vector) != self.embedding_dim:
                        raise ValueError(
                            "Embedding backend returned vectors with unexpected "
                            "dimension"
                        )
                    normalized = self._normalize(vector)
                    self.cache.set(key, normalized)
                    results[index] = self._make_embedding(document, normalized, key)

            if progress_callback is not None:
                progress_callback(min(start + active_batch_size, total), total)

        return [result for result in results if result is not None]

    def cache_key(self, document: DocEmbeddingInput) -> str:
        payload = "\n".join(
            [
                document.parent_symbol_id,
                document.source_type,
                document.source_path or "",
                document.text,
            ]
        )
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        return f"{self.model_name}:doc:{digest}"

    def _make_embedding(
        self,
        document: DocEmbeddingInput,
        vector: list[float],
        cache_key: str,
    ) -> DocEmbedding:
        return DocEmbedding(
            text=document.text,
            vector=list(vector),
            parent_symbol_id=document.parent_symbol_id,
            source_type=document.source_type,
            model_name=self.model_name,
            cache_key=cache_key,
            source_path=document.source_path,
            start_line=document.start_line,
            end_line=document.end_line,
        )

    def _normalize(self, vector: list[float]) -> list[float]:
        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            return list(vector)
        return [value / norm for value in vector]
