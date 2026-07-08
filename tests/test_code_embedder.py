"""Tests for the code embedding pipeline."""

import math

import pytest

from src.reporag.embedding.code_embedder import CodeEmbedder, EmbeddingCache


class FakeBackend:
    def __init__(self, *, device: str = "cpu", dimensions: int = 768) -> None:
        self.model_name = "fake-code-model"
        self.device = device
        self.dimensions = dimensions
        self.calls: list[list[str]] = []

    def embed_batch(self, code_batch: list[str]) -> list[list[float]]:
        self.calls.append(list(code_batch))
        vectors: list[list[float]] = []
        for index, code in enumerate(code_batch, start=1):
            vector = [0.0] * self.dimensions
            vector[0] = float(len(code) or 1)
            if self.dimensions > 1:
                vector[1] = float(index)
            vectors.append(vector)
        return vectors


class ShortBatchBackend(FakeBackend):
    def embed_batch(self, code_batch: list[str]) -> list[list[float]]:
        super().embed_batch(code_batch)
        return []


def l2_norm(vector: list[float]) -> float:
    return math.sqrt(sum(value * value for value in vector))


def test_embed_returns_normalized_768_dim_vector() -> None:
    backend = FakeBackend()
    embedder = CodeEmbedder(backend=backend)

    vector = embedder.embed("def hello():\n    return 42\n")

    assert len(vector) == 768
    assert l2_norm(vector) == pytest.approx(1.0)
    assert backend.calls == [["def hello():\n    return 42\n"]]


def test_embed_batch_uses_configurable_batch_size() -> None:
    backend = FakeBackend()
    embedder = CodeEmbedder(backend=backend, batch_size=2)

    results = embedder.embed_batch(["a()", "b()", "c()", "d()", "e()"])

    assert [len(call) for call in backend.calls] == [2, 2, 1]
    assert len(results) == 5
    assert all(len(result.vector) == 768 for result in results)
    assert all(l2_norm(result.vector) == pytest.approx(1.0) for result in results)


def test_cache_avoids_recomputing_same_code() -> None:
    backend = FakeBackend()
    cache = EmbeddingCache()
    embedder = CodeEmbedder(backend=backend, cache=cache)

    first = embedder.embed("def cached():\n    return True\n")
    second = embedder.embed("def cached():\n    return True\n")

    assert first == second
    assert len(cache) == 1
    assert len(backend.calls) == 1


@pytest.mark.parametrize("device", ["cpu", "cuda"])
def test_device_comes_from_backend(device: str) -> None:
    embedder = CodeEmbedder(backend=FakeBackend(device=device))

    assert embedder.device == device


def test_invalid_batch_size_raises() -> None:
    with pytest.raises(ValueError, match="batch_size"):
        CodeEmbedder(backend=FakeBackend(), batch_size=0)


def test_backend_wrong_batch_length_raises() -> None:
    embedder = CodeEmbedder(backend=ShortBatchBackend())

    with pytest.raises(ValueError, match="wrong batch length"):
        embedder.embed_batch(["def one():\n    pass\n"])


def test_backend_wrong_dimension_raises() -> None:
    embedder = CodeEmbedder(backend=FakeBackend(dimensions=3))

    with pytest.raises(ValueError, match="unexpected dimension"):
        embedder.embed("def too_short():\n    pass\n")
