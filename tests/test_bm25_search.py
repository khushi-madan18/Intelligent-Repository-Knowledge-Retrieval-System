"""Tests for BM25 sparse keyword search."""

from src.reporag.embedding.index_builder import (
    BM25Index,
    CodeAwareTokenizer,
    IndexDocument,
)
from src.reporag.retrieval.bm25_search import BM25Searcher, normalize_identifier
from src.reporag.retrieval.vector_search import VectorSearchFilters, VectorSearchResult


def build_index() -> BM25Index:
    index = BM25Index()
    index.add_or_update(
        [
            IndexDocument(
                id="symbol:authenticate_user",
                text="def authenticate_user(credentials): return token",
                vector=[1.0],
                content_type="code",
                metadata={
                    "source_path": "src/auth.py",
                    "start_line": 10,
                    "end_line": 14,
                    "symbol_id": "symbol:authenticate_user",
                    "symbol_name": "authenticate_user",
                    "symbol_type": "function",
                    "language": "python",
                },
            ),
            IndexDocument(
                id="symbol:AuthService",
                text="class AuthService: def authenticate(self): pass",
                vector=[1.0],
                content_type="code",
                metadata={
                    "source_path": "src/service.py",
                    "start_line": 2,
                    "end_line": 20,
                    "symbol_id": "symbol:AuthService",
                    "symbol_name": "AuthService",
                    "symbol_type": "class",
                    "language": "python",
                },
            ),
            IndexDocument(
                id="doc:auth",
                text="Authenticate users with credentials and sessions.",
                vector=[1.0],
                content_type="doc",
                metadata={
                    "source_path": "README.md",
                    "parent_symbol_id": "readme:auth",
                    "language": "markdown",
                },
            ),
        ]
    )
    return index


def test_exact_identifier_query_returns_defining_function_top_1() -> None:
    searcher = BM25Searcher(build_index())

    response = searcher.search("authenticate_user", top_k=3)

    assert response.results[0].id == "symbol:authenticate_user"
    assert response.results[0].payload["exact_name_match"] is True
    assert response.results[0].file_path == "src/auth.py"
    assert response.results[0].start_line == 10
    assert response.results[0].end_line == 14
    assert response.results[0].symbol == "symbol:authenticate_user"
    assert (
        response.results[0].chunk_text
        == "def authenticate_user(credentials): return token"
    )


def test_code_aware_query_tokenization_matches_indexing() -> None:
    searcher = BM25Searcher(build_index())

    assert searcher.tokenize_query("authenticateUser") == CodeAwareTokenizer().tokenize(
        "authenticateUser"
    )
    assert searcher.tokenize_query("authenticate_user") == [
        "authenticate",
        "user",
    ]


def test_boosting_exact_class_name_match_works() -> None:
    boosted = BM25Searcher(build_index(), exact_name_boost=10.0)
    unboosted = BM25Searcher(build_index(), exact_name_boost=0.0)

    boosted_result = boosted.search("AuthService", top_k=1).results[0]
    unboosted_result = unboosted.search("AuthService", top_k=1).results[0]

    assert boosted_result.id == "symbol:AuthService"
    assert boosted_result.payload["exact_name_match"] is True
    assert boosted_result.score == unboosted_result.score + 10.0


def test_returns_same_result_schema_as_vector_search() -> None:
    searcher = BM25Searcher(build_index())

    result = searcher.search("credentials", top_k=1).results[0]

    assert isinstance(result, VectorSearchResult)
    assert result.collection_name == "bm25"
    assert result.content_type == "code"
    assert "bm25_score" in result.payload


def test_bm25_filters_use_vector_search_filter_shape() -> None:
    searcher = BM25Searcher(build_index())

    response = searcher.search(
        "authenticate",
        top_k=5,
        filters=VectorSearchFilters(language="markdown", file_path="README.md"),
    )

    assert [result.id for result in response.results] == ["doc:auth"]


def test_normalize_identifier_handles_qualified_names() -> None:
    assert normalize_identifier("symbol:AuthService.authenticate_user") == (
        "symbolauthserviceauthenticateuser"
    )


def test_invalid_top_k_raises() -> None:
    searcher = BM25Searcher(build_index())

    try:
        searcher.search("query", top_k=0)
    except ValueError as exc:
        assert "top_k" in str(exc)
    else:
        raise AssertionError("Expected invalid top_k to fail")
