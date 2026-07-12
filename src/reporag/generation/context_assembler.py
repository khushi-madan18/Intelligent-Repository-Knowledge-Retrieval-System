"""Assemble retrieved code chunks into structured prompt context."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.reporag.retrieval.fusion import result_payload, result_score, result_text


@dataclass(frozen=True)
class ContextChunk:
    """Normalized code/document chunk for prompt context assembly."""

    id: str
    file_path: str
    start_line: int
    end_line: int
    text: str
    score: float = 0.0
    payload: dict[str, Any] | None = None


@dataclass(frozen=True)
class AssembledContext:
    """Final prompt context payload."""

    text: str
    chunks: list[ContextChunk]
    token_count: int
    truncated: bool


class ContextAssembler:
    """Order, deduplicate, format, and truncate retrieved chunks."""

    def __init__(self, *, max_tokens: int = 4000) -> None:
        if max_tokens < 1:
            raise ValueError("max_tokens must be at least 1")
        self.max_tokens = max_tokens

    def assemble(
        self, results: list[Any], *, max_tokens: int | None = None
    ) -> AssembledContext:
        """Build prompt context from retrieval results."""

        budget = max_tokens or self.max_tokens
        if budget < 1:
            raise ValueError("max_tokens must be at least 1")

        chunks = [self._normalize_result(result) for result in results]
        chunks = [chunk for chunk in chunks if chunk.text.strip()]
        merged_chunks = self._merge_overlaps(chunks)
        prioritized = sorted(merged_chunks, key=lambda chunk: chunk.score, reverse=True)

        selected: list[ContextChunk] = []
        token_count = 0
        truncated = False
        for chunk in prioritized:
            formatted = self._format_chunk(chunk)
            chunk_tokens = estimate_tokens(formatted)
            if selected and token_count + chunk_tokens > budget:
                truncated = True
                continue
            if not selected and chunk_tokens > budget:
                selected.append(self._truncate_chunk(chunk, budget))
                token_count = estimate_tokens(self._format_chunk(selected[-1]))
                truncated = True
                break
            selected.append(chunk)
            token_count += chunk_tokens

        ordered = sorted(
            selected,
            key=lambda chunk: (chunk.file_path, chunk.start_line, chunk.end_line),
        )
        text = "\n\n".join(self._format_chunk(chunk) for chunk in ordered)
        return AssembledContext(
            text=text,
            chunks=ordered,
            token_count=estimate_tokens(text),
            truncated=truncated,
        )

    def _normalize_result(self, result: Any) -> ContextChunk:
        payload = result_payload(result)
        file_path = (
            getattr(result, "file_path", None)
            or payload.get("source_path")
            or payload.get("file_path")
            or "unknown"
        )
        start_line = int(
            getattr(result, "start_line", None) or payload.get("start_line") or 1
        )
        end_line = int(
            getattr(result, "end_line", None) or payload.get("end_line") or start_line
        )
        return ContextChunk(
            id=str(getattr(result, "id", None) or payload.get("id") or file_path),
            file_path=str(file_path),
            start_line=start_line,
            end_line=max(end_line, start_line),
            text=result_text(result),
            score=result_score(result),
            payload=payload,
        )

    def _merge_overlaps(self, chunks: list[ContextChunk]) -> list[ContextChunk]:
        grouped: dict[str, list[ContextChunk]] = {}
        for chunk in chunks:
            grouped.setdefault(chunk.file_path, []).append(chunk)

        merged: list[ContextChunk] = []
        for file_path, file_chunks in grouped.items():
            ordered = sorted(
                file_chunks, key=lambda chunk: (chunk.start_line, chunk.end_line)
            )
            active: ContextChunk | None = None
            for chunk in ordered:
                if active is None:
                    active = chunk
                    continue
                if chunk.start_line <= active.end_line + 1:
                    active = self._merge_pair(active, chunk)
                    continue
                merged.append(active)
                active = chunk
            if active is not None:
                merged.append(active)
        return merged

    def _merge_pair(self, left: ContextChunk, right: ContextChunk) -> ContextChunk:
        left_lines = left.text.splitlines()
        right_lines = right.text.splitlines()
        overlap = max(0, left.end_line - right.start_line + 1)
        merged_lines = left_lines + right_lines[overlap:]
        return ContextChunk(
            id=left.id if left.score >= right.score else right.id,
            file_path=left.file_path,
            start_line=min(left.start_line, right.start_line),
            end_line=max(left.end_line, right.end_line),
            text="\n".join(merged_lines),
            score=max(left.score, right.score),
            payload={**(left.payload or {}), **(right.payload or {})},
        )

    def _format_chunk(self, chunk: ContextChunk) -> str:
        header = f"### {chunk.file_path}:{chunk.start_line}-{chunk.end_line}"
        numbered_lines = [
            f"{line_number}: {line}"
            for line_number, line in zip(
                range(
                    chunk.start_line, chunk.start_line + len(chunk.text.splitlines())
                ),
                chunk.text.splitlines(),
            )
        ]
        return "\n".join([header, *numbered_lines])

    def _truncate_chunk(self, chunk: ContextChunk, max_tokens: int) -> ContextChunk:
        kept_lines: list[str] = []
        for line in chunk.text.splitlines():
            candidate = "\n".join(kept_lines + [line])
            candidate_chunk = ContextChunk(
                id=chunk.id,
                file_path=chunk.file_path,
                start_line=chunk.start_line,
                end_line=chunk.start_line + len(kept_lines),
                text=candidate,
                score=chunk.score,
                payload=chunk.payload,
            )
            if estimate_tokens(self._format_chunk(candidate_chunk)) > max_tokens:
                break
            kept_lines.append(line)
        return ContextChunk(
            id=chunk.id,
            file_path=chunk.file_path,
            start_line=chunk.start_line,
            end_line=chunk.start_line + max(len(kept_lines) - 1, 0),
            text="\n".join(kept_lines),
            score=chunk.score,
            payload=chunk.payload,
        )


def estimate_tokens(text: str) -> int:
    """Cheap token estimate good enough for context-window budgeting."""

    return len(text.split())
