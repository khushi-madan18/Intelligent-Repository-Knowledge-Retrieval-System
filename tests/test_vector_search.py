"""Tests for vector semantic search."""

from src.reporag.embedding.index_builder import IndexDocument
from src.reporag.retrieval.vector_search import (
    InMemoryVectorSearchBackend,
    VectorSearchFilters,
    VectorSearcher,
    cosine_similarity,
)


class FakeQueryEmbedder:
    def __init__(self, vectors: dict[str, list[float]] | None = None) -> None:
        self.vectors = vectors or {}
        self.calls: list[str] = []

    def embed(self, text: str) -> list[float]:
        self.calls.append(text)
        return self.vectors.get(text, [1.0, 0.0, 0.0])


def make_backend() -> InMemoryVectorSearchBackend:
    backend = InMemoryVectorSearchBackend()
    backend.add_documents(
        "code",
        [
            IndexDocument(
                id="code:auth",
                text="def authenticate_user(): return token",
                vector=[1.0, 0.0, 0.0],
                content_type="code",
                metadata={
                    "source_path": "src/auth.py",
                    "start_line": 10,
                    "end_line": 14,
                    "symbol_id": "symbol:authenticate_user",
                    "symbol_type": "function",
                    "language": "python",
                },
            ),
            IndexDocument(
                id="code:repo",
                text="class RepositoryStore: pass",
                vector=[0.1, 0.9, 0.0],
                content_type="code",
                metadata={
                    "source_path": "src/repository.py",
                    "start_line": 2,
                    "end_line": 8,
                    "symbol_id": "symbol:RepositoryStore",
                    "symbol_type": "class",
                    "language": "python",
                },
            ),
            IndexDocument(
                id="code:js",
                text="function authenticateUser() {}",
                vector=[0.8, 0.2, 0.0],
                content_type="code",
                metadata={
                    "source_path": "web/auth.js",
                    "start_line": 1,
                    "end_line": 3,
                    "symbol_id": "symbol:authenticateUser",
                    "symbol_type": "function",
                    "language": "javascript",
                },
            ),
        ],
    )
    backend.add_documents(
        "docs",
        [
            IndexDocument(
                id="doc:auth",
                text="Authenticate a user and return an access token.",
                vector=[0.95, 0.05, 0.0],
                content_type="doc",
                metadata={
                    "source_path": "src/auth.py",
                    "start_line": 11,
                    "end_line": 12,
                    "parent_symbol_id": "symbol:authenticate_user",
                    "symbol_type": "function",
                    "language": "python",
                },
            ),
            IndexDocument(
                id="doc:readme",
                text="Repository setup instructions.",
                vector=[0.0, 1.0, 0.0],
                content_type="doc",
                metadata={
                    "source_path": "README.md",
                    "parent_symbol_id": "readme:setup",
                    "language": "markdown",
                },
            ),
        ],
    )
    return backend


def test_vector_search_returns_top_k_ranked_by_cosine_similarity() -> None:
    searcher = VectorSearcher(
        query_embedder=FakeQueryEmbedder(),
        backend=make_backend(),
        code_collection_name="code",
        doc_collection_name="docs",
    )

    response = searcher.search("auth query", top_k=2)

    assert [result.id for result in response.results] == ["code:auth", "doc:auth"]
    assert response.results[0].score >= response.results[1].score
    assert response.elapsed_ms < 100


def test_payloads_include_file_lines_symbol_and_chunk_text() -> None:
    searcher = VectorSearcher(
        query_embedder=FakeQueryEmbedder(),
        backend=make_backend(),
        code_collection_name="code",
        doc_collection_name="docs",
    )

    result = searcher.search("auth query", top_k=1).results[0]

    assert result.file_path == "src/auth.py"
    assert result.start_line == 10
    assert result.end_line == 14
    assert result.symbol == "symbol:authenticate_user"
    assert result.symbol_type == "function"
    assert result.chunk_text == "def authenticate_user(): return token"


def test_filtering_by_language_file_path_and_symbol_type_works() -> None:
    searcher = VectorSearcher(
        query_embedder=FakeQueryEmbedder(),
        backend=make_backend(),
        code_collection_name="code",
        doc_collection_name="docs",
    )

    response = searcher.search(
        "auth query",
        top_k=5,
        filters=VectorSearchFilters(
            language="python",
            file_path="src/repository.py",
            symbol_type="class",
        ),
    )

    assert [result.id for result in response.results] == ["code:repo"]


def test_searches_code_and_doc_collections_separately_then_merges() -> None:
    searcher = VectorSearcher(
        query_embedder=FakeQueryEmbedder({"setup": [0.0, 1.0, 0.0]}),
        backend=make_backend(),
        code_collection_name="code",
        doc_collection_name="docs",
    )

    response = searcher.search("setup", top_k=3)

    assert [result.id for result in response.results] == [
        "doc:readme",
        "code:repo",
        "code:js",
    ]


def test_can_search_only_code_or_only_docs() -> None:
    searcher = VectorSearcher(
        query_embedder=FakeQueryEmbedder(),
        backend=make_backend(),
        code_collection_name="code",
        doc_collection_name="docs",
    )

    code_results = searcher.search("auth query", top_k=5, search_docs=False).results
    doc_results = searcher.search("auth query", top_k=5, search_code=False).results

    assert {result.content_type for result in code_results} == {"code"}
    assert {result.content_type for result in doc_results} == {"doc"}


def test_invalid_top_k_raises() -> None:
    searcher = VectorSearcher(
        query_embedder=FakeQueryEmbedder(),
        backend=make_backend(),
        code_collection_name="code",
        doc_collection_name="docs",
    )

    try:
        searcher.search("query", top_k=0)
    except ValueError as exc:
        assert "top_k" in str(exc)
    else:
        raise AssertionError("Expected invalid top_k to fail")


def test_cosine_similarity_handles_zero_and_mismatched_vectors() -> None:
    assert cosine_similarity([1.0, 0.0], [1.0, 0.0]) == 1.0
    assert cosine_similarity([0.0, 0.0], [1.0, 0.0]) == 0.0
    assert cosine_similarity([1.0], [1.0, 0.0]) == 0.0


def test_in_memory_top_20_latency_stays_under_100ms() -> None:
    backend = InMemoryVectorSearchBackend()
    backend.add_documents(
        "code",
        [
            IndexDocument(
                id=f"code:{index}",
                text=f"def symbol_{index}(): pass",
                vector=[1.0, float(index % 10) / 100.0, 0.0],
                content_type="code",
                metadata={
                    "source_path": f"src/file_{index}.py",
                    "symbol_type": "function",
                    "language": "python",
                },
            )
            for index in range(1000)
        ],
    )
    searcher = VectorSearcher(
        query_embedder=FakeQueryEmbedder(),
        backend=backend,
        code_collection_name="code",
        doc_collection_name="docs",
    )

    response = searcher.search("fast query", top_k=20, search_docs=False)

    assert len(response.results) == 20
    assert response.elapsed_ms < 100
