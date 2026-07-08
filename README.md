# Intelligent Repository Knowledge Retrieval System

A code-aware repository intelligence system inspired by the RepoRAG architecture.
The project will ingest repositories, understand code structure, retrieve relevant
code context, and eventually answer questions with file and line citations.

## Current Scope

Project foundation and the first part of repository ingestion are started:

- GitHub Actions CI workflow for PRs/pushes to `main`
- ASCII guard, Ruff, Black, and pytest checks
- Dockerfile for the API server
- Docker Compose stack with API, Neo4j, Qdrant, and PostgreSQL
- Python package scaffold
- Git repository cloning from HTTPS URLs or local paths
- Branch selection and shallow clone support
- Repository file discovery
- Tree-sitter Python parsing with partial ASTs for syntax errors
- Python symbol extraction for functions, classes, methods, and imports
- Semantic code chunking that respects function/class boundaries
- Call graph builder for direct, method, constructor, recursive, and cross-file calls
- Import dependency graph builder with relative import resolution and cycle detection
- Global symbol table with exact, qualified, regex, and file lookups
- Neo4j graph store with NetworkX fallback
- CodeBERT/UniXcoder embedding pipeline with batching and cache
- Sentence-transformers doc embedding pipeline for docstrings, comments, and README sections
- Hybrid Qdrant + BM25 index builder with code-aware tokenization
- Vector semantic search with top-k, filters, and code/doc result merging
- BM25 sparse search with exact function/class name boosting
- Graph traversal retrieval for neighbors, paths, and subgraphs
- Reciprocal Rank Fusion and cross-encoder reranking
- Python AST parsing
- AST-aware chunks that keep functions/classes together
- Unit tests and sample repository

## Quick Start

```bash
cd work/intelligent-repo-knowledge-retrieval-system
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

Without installing dev dependencies, run the current stdlib tests with:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

## Docker

Start the full local stack:

```bash
docker compose up -d
docker compose ps
```

The API listens on `http://localhost:8000`, with a health check at
`/api/v1/health`.

Local service ports:

- API: `8000`
- Neo4j browser: `7474`
- Neo4j bolt: `7687`
- Qdrant HTTP: `16333`
- Qdrant gRPC: `16334`
- Postgres: `5432`

## Pre-Commit

Install and run the local hooks:

```bash
pip install -e ".[dev]"
pre-commit install
pre-commit run --all-files
```

The hooks check trailing whitespace, end-of-file newlines, Ruff, Black,
ASCII-only content, and accidental commits of files under `_internal/`.

## Database

SQLite is the default development database:

```bash
alembic upgrade head
python -c "from src.reporag.db.session import get_db; print('DB OK')"
```

Switch to Postgres by setting `DATABASE_URL`, without changing application code:

```bash
export DATABASE_URL="postgresql+asyncpg://reporag:reporag@localhost:5432/reporag"
```

## Repository Cloning

Clone and discover parseable files:

```bash
python -c "from src.reporag.ingestion.cloner import RepoCloner; cloner = RepoCloner(); manifest = cloner.clone_and_discover('https://github.com/pallets/click', branch='main'); print(f'Found {len(manifest)} files')"
```

Discovery returns entries with `file_path`, `language`, and `size_bytes`.
Supported file extensions can be customized through `RepoCloner(extensions={...})`.

## AST Parsing

Parse Python source with Tree-sitter:

```bash
python -c "from src.reporag.ingestion.parser import ASTParser; parser = ASTParser(); tree = parser.parse('def hello():\n    return 42\n', language='python'); print(tree.root_node.children)"
```

Parser results include `type`, `text`, `start_line`, `end_line`, columns,
error state, and child nodes for each AST node.

## Symbol Extraction

Extract meaningful Python entities from parsed source:

```bash
python -c "from src.reporag.ingestion.parser import ASTParser; from src.reporag.ingestion.symbol_extractor import SymbolExtractor; source='import os\n\ndef hello():\n    return 42\n'; parsed=ASTParser().parse(source, language='python'); symbols=SymbolExtractor().extract(parsed, 'example.py'); print([(s.type, s.name, s.start_line, s.end_line) for s in symbols])"
```

Symbols include names, signatures, docstrings, decorators, line ranges, async
flags, class bases, method metadata, and import details.

## Code Chunking

Chunk parsed and extracted code at semantic boundaries:

```bash
python -c "from src.reporag.ingestion.parser import ASTParser; from src.reporag.ingestion.symbol_extractor import SymbolExtractor; from src.reporag.ingestion.chunker import CodeChunker; source='def hello():\n    return 42\n'; parsed=ASTParser().parse(source, language='python'); symbols=SymbolExtractor().extract(parsed, 'example.py'); chunks=CodeChunker(max_tokens=512).chunk(symbols, source, file_path='example.py', language='python'); print([(c.parent_symbol, c.start_line, c.end_line, c.token_count) for c in chunks])"
```

Large functions are split at blank-line/logical boundaries with the signature
repeated in continuation chunks. Large classes split by method when needed.

## Call Graph

Build caller-to-callee edges from parsed files and extracted symbols:

```bash
python -c "from src.reporag.ingestion.parser import ASTParser; from src.reporag.ingestion.symbol_extractor import SymbolExtractor; from src.reporag.graph.call_graph import CallGraphBuilder, CallGraphInput; source='def outer():\n    return inner()\n\ndef inner():\n    return 42\n'; parsed=ASTParser().parse(source, language='python'); symbols=SymbolExtractor().extract(parsed, 'example.py'); edges=CallGraphBuilder().build([CallGraphInput('example.py', parsed, symbols)]); print([(e.caller, e.callee, e.call_site_line) for e in edges])"
```

Edges include caller, callee, call-site file and line, call text, and resolved
target metadata when a symbol can be matched.

## Dependency Graph

Build module-level import dependency edges:

```bash
python -c "from src.reporag.ingestion.parser import ASTParser; from src.reporag.ingestion.symbol_extractor import SymbolExtractor; from src.reporag.graph.dependency_graph import DependencyGraphBuilder, DependencyGraphInput; source='from app.helpers import normalize\n'; parsed=ASTParser().parse(source, language='python'); symbols=SymbolExtractor().extract(parsed, 'app/service.py'); graph=DependencyGraphBuilder().build([DependencyGraphInput('app/service.py', symbols)]); print([(e.source, e.target, e.imported_names) for e in graph.edges])"
```

Dependency edges include source module, target module, import type, imported
names, source/target files when resolved, star-import warnings, and circular
import chains.

## Symbol Table

Build a central symbol registry from extracted file symbols:

```bash
python -c "from src.reporag.ingestion.parser import ASTParser; from src.reporag.ingestion.symbol_extractor import SymbolExtractor; from src.reporag.graph.symbol_table import SymbolTableBuilder, SymbolTableInput; source='def hello():\n    return 42\n'; parsed=ASTParser().parse(source, language='python'); symbols=SymbolExtractor().extract(parsed, 'example.py'); table=SymbolTableBuilder().build([SymbolTableInput('example.py', symbols)]); print([(r.qualified_name, r.file_path, r.start_line) for r in table.lookup_exact('hello')])"
```

The table supports exact-name, fully qualified-name, regex, and file-path
lookup, plus JSON serialization for persistence.

## Graph Store

Store graph nodes and relationships in Neo4j, or use NetworkX locally:

```bash
python -c "from src.reporag.graph.neo4j_store import GraphNode, NetworkXGraphStore; store=NetworkXGraphStore(); store.create_node(GraphNode('fn:hello', 'Function', {'name': 'hello'})); print(store.query('MATCH (n) RETURN n'))"
```

Supported node labels are `Module`, `Function`, and `Class`. Supported edge
types are `CALLS`, `IMPORTS`, `INHERITS`, and `CONTAINS`.

## Code Embeddings

Install the optional embedding dependencies when you want to load CodeBERT or
UniXcoder from Hugging Face:

```bash
pip install -e ".[embedding]"
```

Generate normalized 768-dimensional vectors:

```bash
python -c "from src.reporag.embedding.code_embedder import CodeEmbedder; embedder=CodeEmbedder(); vector=embedder.embed('def hello():\n    return 42\n'); print(len(vector), embedder.device)"
```

The embedder batches inputs, uses CUDA when available, falls back to CPU, and
caches repeated code strings by model name and content hash.

## Document Embeddings

Embed natural-language repository text and keep it linked to the parent symbol:

```bash
python -c "from src.reporag.embedding.doc_embedder import DocEmbedder; embedder=DocEmbedder(); result=embedder.embed('Return parsed repository files.', parent_symbol_id='symbol:RepoCloner.clone_and_discover'); print(len(result.vector), result.parent_symbol_id)"
```

`DocEmbedder` supports docstrings, comments, and README sections. Empty
docstrings return zero vectors without calling the model, and batch embedding
accepts a progress callback with `(processed, total)`.

## Hybrid Index

Build dense Qdrant points and a sparse BM25 index from code/doc embeddings:

```bash
python -c "from src.reporag.embedding.index_builder import CodeAwareTokenizer; print(CodeAwareTokenizer().tokenize('parseHTTPResponse user_id'))"
```

`HybridIndexBuilder` creates the Qdrant collection payload schema, upserts code
and documentation embeddings with metadata, and keeps a BM25 index updated for
incremental insert/update/delete operations.

## Vector Search

Search code and documentation vector collections, merge the results, and keep
file/line/symbol payloads attached:

```bash
python -c "from src.reporag.retrieval.vector_search import InMemoryVectorSearchBackend, VectorSearcher\nclass Embedder:\n    def embed(self, text): return [1.0, 0.0]\nsearcher=VectorSearcher(query_embedder=Embedder(), backend=InMemoryVectorSearchBackend()); print(searcher.search('auth flow', top_k=5).results)"
```

`VectorSearcher` supports configurable `top_k`, language/file/symbol-type
filters, code-only or docs-only search, and a Qdrant backend for production.

## BM25 Search

Search exact code identifiers with the same result schema as vector search:

```bash
python -c "from src.reporag.embedding.index_builder import BM25Index; from src.reporag.retrieval.bm25_search import BM25Searcher; searcher=BM25Searcher(BM25Index()); print(searcher.tokenize_query('authenticate_user'))"
```

`BM25Searcher` uses the code-aware tokenizer from indexing, returns top-k BM25
matches, and boosts exact function/class name matches so defining symbols rank
above looser keyword matches.

## Graph Retrieval

Traverse the code knowledge graph for structural context:

```bash
python -c "from src.reporag.graph.neo4j_store import NetworkXGraphStore; from src.reporag.retrieval.graph_traversal import GraphTraversalRetriever; retriever=GraphTraversalRetriever(NetworkXGraphStore()); print(retriever.neighbors('symbol:example', hops=1).results)"
```

`GraphTraversalRetriever` supports N-hop neighbors, shortest paths between
symbols, subgraph extraction around symbol sets, and a NetworkX fallback for
local tests.

## Fusion and Reranking

Fuse vector, BM25, and graph ranked lists, then rerank final candidates:

```bash
python -c "from src.reporag.retrieval.fusion import ReciprocalRankFusion; print(ReciprocalRankFusion(k=60).fuse([], top_k=5))"
```

`ReciprocalRankFusion` handles items missing from some sources, tracks source
ranks/scores, and `CrossEncoderReranker` scores `(query, chunk)` pairs for the
final top-k order.

## Roadmap

1. Repo scaffold, tests, config
2. Repository ingestion and AST parsing
3. Code knowledge graph
4. Embeddings and hybrid indexing
5. Retrieval engine
6. Agentic query planner
7. Answer generation with citations
8. API serving and auth
9. Frontend explorer and Q&A interface
10. Evaluation and demo
