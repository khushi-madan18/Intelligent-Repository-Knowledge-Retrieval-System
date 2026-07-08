"""Tests for the hybrid Qdrant + BM25 index builder."""

from src.reporag.embedding.code_embedder import CodeEmbedding
from src.reporag.embedding.doc_embedder import DocEmbedding
from src.reporag.embedding.index_builder import (
    BM25Index,
    CodeAwareTokenizer,
    HybridIndexBuilder,
    IndexDocument,
    QdrantVectorStore,
)


class FakeVectorStore:
    def __init__(self) -> None:
        self.collections: list[tuple[str, int]] = []
        self.upserts: list[tuple[str, list[IndexDocument]]] = []
        self.deletes: list[tuple[str, list[str]]] = []

    def ensure_collection(self, collection_name: str, vector_size: int) -> None:
        self.collections.append((collection_name, vector_size))

    def upsert(self, collection_name: str, documents: list[IndexDocument]) -> None:
        self.upserts.append((collection_name, list(documents)))

    def delete(self, collection_name: str, document_ids: list[str]) -> None:
        self.deletes.append((collection_name, list(document_ids)))


class FakeQdrantCollection:
    def __init__(self, name: str) -> None:
        self.name = name


class FakeQdrantCollections:
    def __init__(self, names: list[str]) -> None:
        self.collections = [FakeQdrantCollection(name) for name in names]


class FakeQdrantClient:
    def __init__(self) -> None:
        self.collection_names: list[str] = []
        self.created_collections: list[dict[str, object]] = []
        self.payload_indexes: list[tuple[str, str, str]] = []

    def get_collections(self) -> FakeQdrantCollections:
        return FakeQdrantCollections(self.collection_names)

    def create_collection(self, **kwargs: object) -> None:
        self.created_collections.append(kwargs)
        self.collection_names.append(str(kwargs["collection_name"]))

    def create_payload_index(
        self,
        *,
        collection_name: str,
        field_name: str,
        field_schema: str,
    ) -> None:
        self.payload_indexes.append((collection_name, field_name, field_schema))


def test_code_aware_tokenizer_splits_snake_and_camel_case() -> None:
    tokens = CodeAwareTokenizer().tokenize(
        "def parseHTTPResponse(user_id): return repoPath"
    )

    assert "parse" in tokens
    assert "http" in tokens
    assert "response" in tokens
    assert "user" in tokens
    assert "id" in tokens
    assert "repo" in tokens
    assert "path" in tokens


def test_bm25_index_searches_and_supports_incremental_updates() -> None:
    bm25 = BM25Index()
    first = IndexDocument(
        id="code:one",
        text="def cloneRepository(): pass",
        vector=[1.0, 0.0],
        content_type="code",
        metadata={"source_path": "cloner.py"},
    )
    second = IndexDocument(
        id="doc:two",
        text="Parse README setup instructions",
        vector=[0.0, 1.0],
        content_type="doc",
        metadata={"parent_symbol_id": "readme:setup"},
    )

    bm25.add_or_update([first, second])
    hits = bm25.search("clone repository", limit=1)

    assert hits[0].document_id == "code:one"
    assert hits[0].metadata["source_path"] == "cloner.py"

    updated = IndexDocument(
        id="code:one",
        text="def uniqueReplacementToken(): pass",
        vector=[1.0, 0.0],
        content_type="code",
    )
    bm25.add_or_update([updated])

    assert bm25.search("clone repository") == []
    assert bm25.search("unique replacement token")[0].document_id == "code:one"

    bm25.delete(["code:one"])
    assert bm25.search("readme setup")[0].document_id == "doc:two"


def test_hybrid_builder_creates_collection_and_upserts_metadata() -> None:
    vector_store = FakeVectorStore()
    bm25 = BM25Index()
    builder = HybridIndexBuilder(
        collection_name="test_embeddings",
        vector_store=vector_store,
        bm25_index=bm25,
    )
    document = IndexDocument(
        id="chunk:1",
        text="def find_symbol(): return symbol",
        vector=[0.2, 0.8],
        content_type="code",
        metadata={"source_path": "symbols.py", "symbol_id": "symbol:find_symbol"},
    )

    builder.build([document])

    assert vector_store.collections == [("test_embeddings", 2)]
    assert vector_store.upserts == [("test_embeddings", [document])]
    assert bm25.search("find symbol")[0].metadata["symbol_id"] == "symbol:find_symbol"


def test_builder_supports_incremental_upsert_and_delete() -> None:
    vector_store = FakeVectorStore()
    builder = HybridIndexBuilder(vector_store=vector_store)

    first = IndexDocument("item:1", "alpha token", [1.0, 0.0], "doc")
    replacement = IndexDocument("item:1", "beta token", [0.0, 1.0], "doc")

    builder.upsert([first])
    builder.upsert([replacement])
    builder.delete(["item:1"])

    assert [len(batch) for _, batch in vector_store.upserts] == [1, 1]
    assert vector_store.deletes == [("reporag_embeddings", ["item:1"])]
    assert builder.bm25_index.search("alpha beta") == []


def test_builder_converts_code_and_doc_embeddings_to_index_documents() -> None:
    vector_store = FakeVectorStore()
    builder = HybridIndexBuilder(vector_store=vector_store)
    code_embedding = CodeEmbedding(
        text="def load_config(): pass",
        vector=[1.0, 0.0],
        model_name="code-model",
        cache_key="code:abc",
    )
    doc_embedding = DocEmbedding(
        text="Load configuration from environment.",
        vector=[0.0, 1.0],
        parent_symbol_id="symbol:load_config",
        source_type="docstring",
        model_name="doc-model",
        cache_key="doc:def",
        source_path="config.py",
        start_line=10,
        end_line=12,
    )

    builder.upsert_code_embeddings(
        [code_embedding],
        metadata_by_id={"code:abc": {"source_path": "config.py"}},
    )
    builder.upsert_doc_embeddings([doc_embedding])

    code_document = vector_store.upserts[0][1][0]
    doc_document = vector_store.upserts[1][1][0]

    assert code_document.content_type == "code"
    assert code_document.metadata["source_path"] == "config.py"
    assert code_document.metadata["model_name"] == "code-model"
    assert doc_document.content_type == "doc"
    assert doc_document.metadata["parent_symbol_id"] == "symbol:load_config"
    assert doc_document.metadata["source_path"] == "config.py"


def test_qdrant_vector_store_creates_collection_with_payload_schema() -> None:
    client = FakeQdrantClient()
    store = QdrantVectorStore(client=client)

    store.ensure_collection("repo_vectors", 768)

    assert client.created_collections[0]["collection_name"] == "repo_vectors"
    assert ("repo_vectors", "content_type", "keyword") in client.payload_indexes
    assert ("repo_vectors", "parent_symbol_id", "keyword") in client.payload_indexes


def test_builder_rejects_mismatched_vector_dimensions() -> None:
    builder = HybridIndexBuilder(vector_store=FakeVectorStore())
    documents = [
        IndexDocument("one", "one", [1.0, 0.0], "code"),
        IndexDocument("two", "two", [1.0, 0.0, 0.0], "code"),
    ]

    try:
        builder.upsert(documents)
    except ValueError as exc:
        assert "same dimension" in str(exc)
    else:
        raise AssertionError("Expected mismatched vector dimensions to fail")
