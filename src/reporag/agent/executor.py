"""Dependency-aware sub-query executor."""

from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from src.reporag.agent.planner import QueryDecomposition, SubQuery
from src.reporag.agent.router import RetrievalStrategy, StrategyRoute, StrategyRouter


@dataclass(frozen=True)
class ExecutionContext:
    """Context forwarded into a sub-query execution step."""

    original_query: str
    sub_query: SubQuery
    route: StrategyRoute
    dependency_results: dict[str, list[Any]]
    previous_results: dict[str, list[Any]]


@dataclass(frozen=True)
class SubQueryExecution:
    """Result of executing one sub-query."""

    sub_query: SubQuery
    route: StrategyRoute
    results: list[Any]
    context_from: dict[str, list[Any]] = field(default_factory=dict)


@dataclass(frozen=True)
class ExecutionPlanResult:
    """Complete execution result for a decomposed query."""

    original_query: str
    steps: list[SubQueryExecution]
    results_by_sub_query: dict[str, list[Any]]


StrategyCallable = Callable[[ExecutionContext], list[Any]]


class SubQueryExecutor:
    """Execute sub-queries in dependency order and forward context."""

    def __init__(
        self,
        *,
        router: StrategyRouter | None = None,
        executors: dict[RetrievalStrategy, StrategyCallable] | None = None,
    ) -> None:
        self.router = router or StrategyRouter()
        self.executors = executors or {}

    def execute(
        self,
        decomposition: QueryDecomposition,
    ) -> ExecutionPlanResult:
        """Execute sub-queries in dependency order."""

        ordered_sub_queries = self._dependency_order(decomposition)
        results_by_sub_query: dict[str, list[Any]] = {}
        steps: list[SubQueryExecution] = []

        for sub_query in ordered_sub_queries:
            route = self.router.route(sub_query)
            dependency_results = {
                dependency_id: results_by_sub_query.get(dependency_id, [])
                for dependency_id in sub_query.context_from
            }
            context = ExecutionContext(
                original_query=decomposition.query,
                sub_query=sub_query,
                route=route,
                dependency_results=dependency_results,
                previous_results=dict(results_by_sub_query),
            )
            results = self._execute_strategy(route.strategy, context)
            results_by_sub_query[sub_query.id] = results
            steps.append(
                SubQueryExecution(
                    sub_query=sub_query,
                    route=route,
                    results=results,
                    context_from=dependency_results,
                )
            )

        return ExecutionPlanResult(
            original_query=decomposition.query,
            steps=steps,
            results_by_sub_query=results_by_sub_query,
        )

    def _execute_strategy(
        self,
        strategy: RetrievalStrategy,
        context: ExecutionContext,
    ) -> list[Any]:
        executor = self.executors.get(strategy)
        if executor is not None:
            return list(executor(context))

        if strategy == "hybrid":
            combined: list[Any] = []
            for fallback_strategy in ("bm25", "vector", "graph"):
                fallback = self.executors.get(fallback_strategy)
                if fallback is not None:
                    combined.extend(fallback(context))
            return combined

        return []

    def _dependency_order(
        self,
        decomposition: QueryDecomposition,
    ) -> list[SubQuery]:
        sub_query_by_id = {
            sub_query.id: sub_query for sub_query in decomposition.sub_queries
        }
        indegree = {sub_query.id: 0 for sub_query in decomposition.sub_queries}
        adjacency: dict[str, list[str]] = defaultdict(list)

        for edge in decomposition.dependency_edges:
            if edge.source not in sub_query_by_id or edge.target not in sub_query_by_id:
                continue
            adjacency[edge.source].append(edge.target)
            indegree[edge.target] += 1

        for sub_query in decomposition.sub_queries:
            for dependency_id in sub_query.context_from:
                if dependency_id not in sub_query_by_id:
                    continue
                if sub_query.id not in adjacency[dependency_id]:
                    adjacency[dependency_id].append(sub_query.id)
                    indegree[sub_query.id] += 1

        queue = deque(
            sub_query.id
            for sub_query in decomposition.sub_queries
            if indegree[sub_query.id] == 0
        )
        ordered_ids: list[str] = []

        while queue:
            sub_query_id = queue.popleft()
            ordered_ids.append(sub_query_id)
            for target_id in adjacency[sub_query_id]:
                indegree[target_id] -= 1
                if indegree[target_id] == 0:
                    queue.append(target_id)

        if len(ordered_ids) != len(sub_query_by_id):
            raise ValueError("Sub-query dependency graph contains a cycle")

        return [sub_query_by_id[sub_query_id] for sub_query_id in ordered_ids]
