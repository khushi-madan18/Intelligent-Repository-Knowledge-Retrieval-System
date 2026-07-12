"""Strategy router for agentic sub-query execution."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from src.reporag.agent.planner import SubQuery

RetrievalStrategy = Literal["bm25", "graph", "vector", "hybrid"]


@dataclass(frozen=True)
class StrategyRoute:
    """Routing decision for a sub-query."""

    sub_query_id: str
    strategy: RetrievalStrategy
    reason: str


class StrategyRouter:
    """Route sub-queries to retrieval strategies."""

    def route(self, sub_query: SubQuery) -> StrategyRoute:
        """Pick bm25, graph, vector, or hybrid for a sub-query."""

        text = sub_query.text.lower()

        if self._is_structural_query(sub_query, text):
            return StrategyRoute(
                sub_query_id=sub_query.id,
                strategy="graph",
                reason="Structural/path query benefits from graph traversal.",
            )

        if self._is_identifier_lookup(sub_query, text):
            return StrategyRoute(
                sub_query_id=sub_query.id,
                strategy="bm25",
                reason="Exact identifier lookup benefits from sparse search.",
            )

        if self._is_hybrid_query(sub_query, text):
            return StrategyRoute(
                sub_query_id=sub_query.id,
                strategy="hybrid",
                reason="Evidence query benefits from combined retrieval signals.",
            )

        return StrategyRoute(
            sub_query_id=sub_query.id,
            strategy="vector",
            reason="Semantic query benefits from vector search.",
        )

    def _is_identifier_lookup(self, sub_query: SubQuery, text: str) -> bool:
        if sub_query.expected_answer_type == "symbol":
            return True
        if re.search(
            r"\b(where|find|show)\b.*\b(function|class|method|symbol)\b", text
        ):
            return True
        return bool(
            re.fullmatch(
                r"[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*",
                sub_query.text.strip("`'\" "),
            )
        )

    def _is_structural_query(self, sub_query: SubQuery, text: str) -> bool:
        if sub_query.expected_answer_type == "path":
            return True
        return bool(
            re.search(
                r"\b(path|trace|call chain|calls|imports|dependencies|flow|graph)\b",
                text,
            )
        )

    def _is_hybrid_query(self, sub_query: SubQuery, text: str) -> bool:
        if sub_query.expected_answer_type == "evidence":
            return True
        return bool(re.search(r"\b(collect|supporting|evidence|combine)\b", text))
