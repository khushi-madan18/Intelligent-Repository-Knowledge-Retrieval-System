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
- Python AST parsing
- Symbol extraction for functions, classes, methods, and imports
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
