# Project Plan

## Milestone 1: Foundation

Status: issue 1 implemented

- [x] Create Python package scaffold
- [x] Add basic configuration
- [x] Add sample repository for tests
- [x] Add runnable ingestion tests
- [x] Add Dockerfile for API server
- [x] Add docker-compose services: api, neo4j, qdrant, postgres
- [x] Add `.env.example`
- [x] Add CI workflow for push/PR to main
- [x] Add ASCII guard
- [x] Add formatting and linting setup
- [x] Add pre-commit hooks
- [x] Add internal-data guard

## Milestone 1.5: Database Foundation

Status: issue 3 implemented

- [x] Add SQLAlchemy models: Repository, IngestionJob, User, QueryLog
- [x] Add async database session factory
- [x] Add SQLite default database URL
- [x] Add Postgres-ready database URL switching
- [x] Add Alembic migration environment
- [x] Add initial schema migration

## Milestone 2: Repository Understanding

Status: started

- [x] Discover local repository files
- [x] Add remote Git clone support
- [x] Add branch selection and shallow clone support
- [x] Add configurable source extension discovery
- [x] Add Tree-sitter parser interface
- [x] Parse Python source into structured AST nodes
- [x] Return partial ASTs for syntax errors
- [x] Parse Python files into ASTs
- [x] Extract functions, classes, methods, and imports
- [x] Add symbol metadata: signatures, docstrings, decorators, imports, line ranges
- [x] Create AST-aware chunks
- [x] Split oversized functions/classes at semantic boundaries with signature overlap
- [ ] Add call extraction inside functions
- [ ] Add JavaScript/TypeScript parser support

## Milestone 3: Knowledge Graph

Status: started

- [x] Build symbol table across all parsed files
- [x] Add exact, qualified, regex, and file-path symbol lookups
- [x] Add JSON serialization for symbol registry
- [x] Build import dependency graph
- [x] Resolve absolute and relative imports
- [x] Detect circular import chains
- [x] Build function call graph
- [x] Resolve direct, method, recursive, and cross-file calls
- [x] Add Neo4j graph store wrapper
- [x] Add NetworkX graph store fallback
- [x] Add in-memory graph query interface

## Milestone 4: Retrieval

Status: started

- [x] Add BM25 keyword retrieval
- [x] Add vector embedding interface
- [x] Add CodeBERT/UniXcoder embedding backend
- [x] Add batch embedding with CPU/GPU device support
- [x] Add L2 normalization and embedding cache
- [x] Add sentence-transformers document embedding backend
- [x] Link documentation embeddings to parent symbols
- [x] Add document embedding progress callbacks
- [x] Add Qdrant vector collection builder
- [x] Add hybrid index incremental updates
- [x] Add vector semantic search over code and docs
- [x] Add retrieval filters for language, file, and symbol type
- [x] Add BM25 search with exact identifier boosting
- [x] Add graph neighbor traversal
- [x] Add shortest path and subgraph retrieval
- [x] Add result fusion
- [x] Add reranking interface

## Milestone 4.5: Agentic Query Planning

Status: started

- [x] Add query classifier for simple lookup, multi-hop, and exploratory queries
- [x] Add confidence scores and low-confidence fallback
- [x] Add few-shot LLM classifier prompt
- [x] Add multi-hop query decomposer
- [x] Add ordered sub-queries with dependency edges
- [x] Add LangGraph-compatible decomposition state machine
- [x] Add retrieval strategy planner
- [x] Add dependency-aware sub-query executor

## Milestone 4.75: Answer Context Assembly

Status: started

- [x] Add context assembler for retrieved chunks
- [x] Add overlap deduplication and line-numbered formatting
- [x] Add context-window truncation with priority ranking
- [x] Add code-aware prompt templates by query type
- [x] Add citation instructions and few-shot cited examples
- [x] Add prompt context-window budgeting
- [x] Add answer generator with citations
- [x] Add citation extraction and validation
- [x] Add configurable OpenAI/Anthropic generation clients
- [x] Add graceful LLM error handling

## Milestone 5: API and UI

Status: started

- [x] Add FastAPI endpoints
- [x] Add query endpoint with citations
- [x] Add repository ingestion and listing endpoints
- [x] Add health endpoint with component status
- [x] Add OpenAPI docs route
- [ ] Add repository explorer UI
- [ ] Add Q&A interface
