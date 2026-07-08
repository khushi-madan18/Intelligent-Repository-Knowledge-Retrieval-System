"""Tests for the natural-language document embedding pipeline."""

import math

import pytest

from src.reporag.embedding.code_embedder import EmbeddingCache
from src.reporag.embedding.doc_embedder import DocEmbedder, DocEmbeddingInput


class FakeDocBackend:
    def __init__(self, *, device: str = "cpu", dimensions: int = 384) -> None:
        self.model_name = "fake-doc-model"
        self.device = device
        self.embedding_dim = dimensions
        self.calls: list[list[str]] = []

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        vectors: list[list[float]] = []
        for index, text in enumerate(texts, start=1):
            vector = [0.0] * self.embedding_dim
            vector[0] = float(len(text) or 1)
            if self.embedding_dim > 1:
                vector[1] = float(index)
            vectors.append(vector)
        return vectors


class ShortDocBackend(FakeDocBackend):
    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        super().embed_batch(texts)
        return []


def l2_norm(vector: list[float]) -> float:
    return math.sqrt(sum(value * value for value in vector))


def test_embed_docstring_links_vector_to_parent_symbol() -> None:
    backend = FakeDocBackend()
    embedder = DocEmbedder(backend=backend)

    result = embedder.embed(
        "Return the parsed repository manifest.",
        parent_symbol_id="symbol:RepoCloner.clone_and_discover",
        source_path="src/reporag/ingestion/cloner.py",
        start_line=42,
        end_line=44,
    )

    assert len(result.vector) == 384
    assert l2_norm(result.vector) == pytest.approx(1.0)
    assert result.parent_symbol_id == "symbol:RepoCloner.clone_and_discover"
    assert result.source_type == "docstring"
    assert result.source_path == "src/reporag/ingestion/cloner.py"
    assert result.start_line == 42
    assert result.end_line == 44


def test_embed_batch_supports_comments_readme_and_progress_callback() -> None:
    backend = FakeDocBackend()
    embedder = DocEmbedder(backend=backend, batch_size=2)
    progress: list[tuple[int, int]] = []
    documents = [
        DocEmbeddingInput("Explains setup.", "readme:intro", "readme", "README.md"),
        DocEmbeddingInput("Validate user input.", "symbol:validate", "comment"),
        DocEmbeddingInput("Create database rows.", "symbol:create_rows", "docstring"),
    ]

    results = embedder.embed_batch(
        documents,
        progress_callback=lambda processed, total: progress.append((processed, total)),
    )

    assert [len(call) for call in backend.calls] == [2, 1]
    assert progress == [(2, 3), (3, 3)]
    assert [result.parent_symbol_id for result in results] == [
        "readme:intro",
        "symbol:validate",
        "symbol:create_rows",
    ]
    assert all(l2_norm(result.vector) == pytest.approx(1.0) for result in results)


def test_empty_docstring_returns_zero_vector_without_backend_call() -> None:
    backend = FakeDocBackend()
    embedder = DocEmbedder(backend=backend)

    result = embedder.embed("   ", parent_symbol_id="symbol:empty")

    assert result.vector == [0.0] * 384
    assert result.parent_symbol_id == "symbol:empty"
    assert backend.calls == []


def test_cache_avoids_recomputing_document_embeddings() -> None:
    backend = FakeDocBackend()
    cache = EmbeddingCache()
    embedder = DocEmbedder(backend=backend, cache=cache)
    document = DocEmbeddingInput("Normalize query text.", "symbol:normalize")

    first = embedder.embed_batch([document])[0]
    second = embedder.embed_batch([document])[0]

    assert first.vector == second.vector
    assert len(cache) == 1
    assert len(backend.calls) == 1


@pytest.mark.parametrize("device", ["cpu", "cuda"])
def test_device_comes_from_backend(device: str) -> None:
    embedder = DocEmbedder(backend=FakeDocBackend(device=device))

    assert embedder.device == device


def test_empty_batch_reports_zero_progress() -> None:
    embedder = DocEmbedder(backend=FakeDocBackend())
    progress: list[tuple[int, int]] = []

    assert (
        embedder.embed_batch(
            [],
            progress_callback=lambda processed, total: progress.append(
                (processed, total)
            ),
        )
        == []
    )
    assert progress == [(0, 0)]


def test_invalid_batch_size_raises() -> None:
    with pytest.raises(ValueError, match="batch_size"):
        DocEmbedder(backend=FakeDocBackend(), batch_size=0)


def test_backend_wrong_batch_length_raises() -> None:
    embedder = DocEmbedder(backend=ShortDocBackend())

    with pytest.raises(ValueError, match="wrong batch length"):
        embedder.embed_batch([DocEmbeddingInput("hello", "symbol:hello")])


def test_backend_wrong_dimension_raises() -> None:
    embedder = DocEmbedder(backend=FakeDocBackend(dimensions=3))
    embedder.embedding_dim = 384

    with pytest.raises(ValueError, match="unexpected dimension"):
        embedder.embed("hello", parent_symbol_id="symbol:hello")
