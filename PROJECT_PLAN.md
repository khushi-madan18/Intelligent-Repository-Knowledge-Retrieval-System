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

Status: next

- [ ] Build symbol table across all parsed files
- [ ] Build import dependency graph
- [ ] Build function call graph
- [ ] Add in-memory graph query interface

## Milestone 4: Retrieval

Status: planned

- [ ] Add BM25 keyword retrieval
- [ ] Add vector embedding interface
- [ ] Add result fusion
- [ ] Add reranking interface

## Milestone 5: API and UI

Status: planned

- [ ] Add FastAPI endpoints
- [ ] Add query endpoint with citations
- [ ] Add repository explorer UI
- [ ] Add Q&A interface
