"""Repository query API routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from src.reporag.agent.planner import QueryCategory
from src.reporag.generation.context_assembler import AssembledContext, ContextChunk
from src.reporag.generation.generator import GenerationResult

router = APIRouter(prefix="/query", tags=["query"])


class QueryContextChunk(BaseModel):
    """Retrieved context chunk supplied to the query endpoint."""

    id: str
    file_path: str
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    text: str
    score: float = 0.0
    payload: dict[str, Any] | None = None


class QueryRequest(BaseModel):
    """Question request for repository Q&A."""

    query: str = Field(min_length=1)
    repository_id: str | None = None
    query_type: QueryCategory = "exploratory"
    context: list[QueryContextChunk] = Field(default_factory=list)


class CitationResponse(BaseModel):
    """Validated line-level citation."""

    file_path: str
    start_line: int
    end_line: int
    marker: str
    valid: bool
    reason: str


class QueryMetadata(BaseModel):
    """Metadata returned with a query answer."""

    repository_id: str | None = None
    query_type: QueryCategory
    citation_coverage: float
    context_chunks: int
    used_generator: bool
    error: str | None = None


class QueryResponse(BaseModel):
    """Structured query answer response."""

    answer: str
    citations: list[CitationResponse]
    metadata: QueryMetadata


@router.post("", response_model=QueryResponse)
async def query_repository(
    request: QueryRequest, app_request: Request
) -> QueryResponse:
    """Answer a repository question with citations and metadata."""

    context = _assemble_request_context(request.context)

    handler = getattr(app_request.app.state, "query_handler", None)
    if handler is not None:
        result = handler(request, context)
        if isinstance(result, QueryResponse):
            return result
        if isinstance(result, GenerationResult):
            return _generation_to_response(result, request, used_generator=True)

    generator = getattr(app_request.app.state, "answer_generator", None)
    if generator is not None:
        result = generator.generate(
            request.query,
            query_type=request.query_type,
            context=context,
        )
        return _generation_to_response(result, request, used_generator=True)

    return QueryResponse(
        answer="No LLM generator is configured for this API process.",
        citations=[],
        metadata=QueryMetadata(
            repository_id=request.repository_id,
            query_type=request.query_type,
            citation_coverage=0.0,
            context_chunks=len(context.chunks),
            used_generator=False,
            error=None,
        ),
    )


def _assemble_request_context(chunks: list[QueryContextChunk]) -> AssembledContext:
    context_chunks = [
        ContextChunk(
            id=chunk.id,
            file_path=chunk.file_path,
            start_line=chunk.start_line,
            end_line=chunk.end_line,
            text=chunk.text,
            score=chunk.score,
            payload=chunk.payload,
        )
        for chunk in chunks
    ]
    text = "\n\n".join(_format_chunk(chunk) for chunk in context_chunks)
    return AssembledContext(
        text=text,
        chunks=context_chunks,
        token_count=len(text.split()),
        truncated=False,
    )


def _format_chunk(chunk: ContextChunk) -> str:
    header = f"### {chunk.file_path}:{chunk.start_line}-{chunk.end_line}"
    numbered_lines = [
        f"{line_number}: {line}"
        for line_number, line in zip(
            range(chunk.start_line, chunk.start_line + len(chunk.text.splitlines())),
            chunk.text.splitlines(),
        )
    ]
    return "\n".join([header, *numbered_lines])


def _generation_to_response(
    result: GenerationResult,
    request: QueryRequest,
    *,
    used_generator: bool,
) -> QueryResponse:
    return QueryResponse(
        answer=result.answer,
        citations=[
            CitationResponse(
                file_path=citation.file_path,
                start_line=citation.start_line,
                end_line=citation.end_line,
                marker=citation.marker,
                valid=citation.valid,
                reason=citation.reason,
            )
            for citation in result.citations
        ],
        metadata=QueryMetadata(
            repository_id=request.repository_id,
            query_type=request.query_type,
            citation_coverage=result.citation_coverage,
            context_chunks=len(request.context),
            used_generator=used_generator,
            error=result.error,
        ),
    )
