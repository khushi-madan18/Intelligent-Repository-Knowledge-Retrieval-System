"""Code embedding pipeline with Hugging Face support and local caching."""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field
from typing import Protocol

DEFAULT_MODEL_NAME = "microsoft/codebert-base"
DEFAULT_EMBEDDING_DIM = 768


class EmbeddingBackend(Protocol):
    """Backend interface used by CodeEmbedder."""

    model_name: str
    device: str

    def embed_batch(self, code_batch: list[str]) -> list[list[float]]:
        """Return one embedding per code string."""


@dataclass(frozen=True)
class CodeEmbedding:
    """Embedding result with source code cache metadata."""

    text: str
    vector: list[float]
    model_name: str
    cache_key: str


@dataclass
class EmbeddingCache:
    """In-memory embedding cache keyed by model and source hash."""

    _vectors: dict[str, list[float]] = field(default_factory=dict)

    def get(self, key: str) -> list[float] | None:
        vector = self._vectors.get(key)
        return list(vector) if vector is not None else None

    def set(self, key: str, vector: list[float]) -> None:
        self._vectors[key] = list(vector)

    def __len__(self) -> int:
        return len(self._vectors)


class HuggingFaceCodeBackend:
    """Hugging Face backend for CodeBERT/UniXcoder style embedding models."""

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL_NAME,
        *,
        device: str | None = None,
        max_length: int = 512,
    ) -> None:
        self.model_name = model_name
        self.max_length = max_length

        try:
            import torch
            from transformers import AutoModel, AutoTokenizer
        except ImportError as exc:
            raise RuntimeError(
                "Install torch and transformers to use HuggingFaceCodeBackend"
            ) from exc

        self._torch = torch
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.model = AutoModel.from_pretrained(model_name).to(self.device)
        self.model.eval()

    def embed_batch(self, code_batch: list[str]) -> list[list[float]]:
        if not code_batch:
            return []

        encoded = self.tokenizer(
            code_batch,
            padding=True,
            truncation=True,
            max_length=self.max_length,
            return_tensors="pt",
        )
        encoded = {key: value.to(self.device) for key, value in encoded.items()}

        with self._torch.no_grad():
            outputs = self.model(**encoded)

        token_embeddings = outputs.last_hidden_state
        attention_mask = encoded["attention_mask"].unsqueeze(-1)
        masked_embeddings = token_embeddings * attention_mask
        summed = masked_embeddings.sum(dim=1)
        counts = attention_mask.sum(dim=1).clamp(min=1)
        vectors = summed / counts

        return vectors.detach().cpu().tolist()


class CodeEmbedder:
    """Embed code strings with batching, CPU/GPU backend support, and caching."""

    def __init__(
        self,
        *,
        model_name: str = DEFAULT_MODEL_NAME,
        batch_size: int = 16,
        embedding_dim: int = DEFAULT_EMBEDDING_DIM,
        backend: EmbeddingBackend | None = None,
        cache: EmbeddingCache | None = None,
    ) -> None:
        if batch_size < 1:
            raise ValueError("batch_size must be at least 1")
        if embedding_dim < 1:
            raise ValueError("embedding_dim must be at least 1")

        self.model_name = model_name
        self.batch_size = batch_size
        self.embedding_dim = embedding_dim
        self.backend = (
            backend
            if backend is not None
            else HuggingFaceCodeBackend(model_name=model_name)
        )
        self.cache = cache if cache is not None else EmbeddingCache()

    @property
    def device(self) -> str:
        return self.backend.device

    def embed(self, code: str) -> list[float]:
        return self.embed_batch([code])[0].vector

    def embed_batch(
        self,
        code_strings: list[str],
        *,
        batch_size: int | None = None,
    ) -> list[CodeEmbedding]:
        """Embed code strings in batches and L2-normalize all vectors."""

        if not code_strings:
            return []

        active_batch_size = batch_size or self.batch_size
        if active_batch_size < 1:
            raise ValueError("batch_size must be at least 1")

        results: list[CodeEmbedding | None] = [None] * len(code_strings)
        uncached: list[tuple[int, str, str]] = []

        for index, code in enumerate(code_strings):
            key = self.cache_key(code)
            cached_vector = self.cache.get(key)
            if cached_vector is not None:
                results[index] = CodeEmbedding(
                    text=code,
                    vector=cached_vector,
                    model_name=self.model_name,
                    cache_key=key,
                )
                continue
            uncached.append((index, code, key))

        for start in range(0, len(uncached), active_batch_size):
            batch_items = uncached[start : start + active_batch_size]
            vectors = self.backend.embed_batch([item[1] for item in batch_items])
            if len(vectors) != len(batch_items):
                raise ValueError("Embedding backend returned the wrong batch length")

            for (index, code, key), vector in zip(batch_items, vectors, strict=True):
                if len(vector) != self.embedding_dim:
                    raise ValueError(
                        "Embedding backend returned vectors with unexpected dimension"
                    )
                normalized = self._normalize(vector)
                self.cache.set(key, normalized)
                results[index] = CodeEmbedding(
                    text=code,
                    vector=normalized,
                    model_name=self.model_name,
                    cache_key=key,
                )

        return [result for result in results if result is not None]

    def cache_key(self, code: str) -> str:
        digest = hashlib.sha256(code.encode("utf-8")).hexdigest()
        return f"{self.model_name}:{digest}"

    def _normalize(self, vector: list[float]) -> list[float]:
        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            return list(vector)
        return [value / norm for value in vector]
