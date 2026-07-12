"""Query planning and classification for retrieval routing."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from src.reporag.config import settings

QueryCategory = Literal["simple-lookup", "multi-hop", "exploratory"]
VALID_CATEGORIES: set[str] = {"simple-lookup", "multi-hop", "exploratory"}

FEW_SHOT_EXAMPLES = [
    (
        "Where is authenticate_user defined?",
        "simple-lookup",
        0.94,
        "Asks for one symbol definition.",
    ),
    (
        "What calls RepositoryStore.save?",
        "simple-lookup",
        0.87,
        "Direct lookup around one named symbol.",
    ),
    (
        "How does a login request flow from API route to database?",
        "multi-hop",
        0.92,
        "Requires following calls across multiple components.",
    ),
    (
        "Find the path between validate_token and refresh_session",
        "multi-hop",
        0.9,
        "Asks for a graph/path traversal.",
    ),
    (
        "Explain the authentication architecture",
        "exploratory",
        0.88,
        "Open-ended overview request.",
    ),
    (
        "What should I read first to understand ingestion?",
        "exploratory",
        0.83,
        "Broad discovery question without a single target.",
    ),
]


class QueryClassifierBackend(Protocol):
    """LLM backend used by QueryClassifier."""

    def complete(self, prompt: str) -> str:
        """Return a JSON classification string."""


@dataclass(frozen=True)
class QueryClassification:
    """Classifier output with confidence and fallback metadata."""

    query: str
    category: QueryCategory
    confidence: float
    reason: str = ""
    raw_category: str | None = None
    used_fallback: bool = False


class OpenAIQueryClassifierBackend:
    """OpenAI chat-completions backend for query classification."""

    def __init__(
        self,
        *,
        model: str | None = None,
        api_key: str | None = None,
    ) -> None:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError(
                "Install openai to use OpenAIQueryClassifierBackend"
            ) from exc

        key = api_key or settings.openai_api_key.get_secret_value()
        self.model = model or settings.llm_model
        self.client = OpenAI(api_key=key)

    def complete(self, prompt: str) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": "Classify repository questions as strict JSON.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0,
        )
        return response.choices[0].message.content or "{}"


class QueryClassifier:
    """Classify user questions for retrieval planning."""

    def __init__(
        self,
        *,
        backend: QueryClassifierBackend | None = None,
        confidence_threshold: float = 0.55,
    ) -> None:
        if not 0 <= confidence_threshold <= 1:
            raise ValueError("confidence_threshold must be between 0 and 1")
        self.backend = backend
        self.confidence_threshold = confidence_threshold

    def classify(self, query: str) -> QueryClassification:
        """Return simple-lookup, multi-hop, or exploratory with confidence."""

        clean_query = query.strip()
        if not clean_query:
            return QueryClassification(
                query=query,
                category="multi-hop",
                confidence=0.0,
                reason="Empty query cannot be classified confidently.",
                raw_category=None,
                used_fallback=True,
            )

        if self.backend is None:
            classification = self._heuristic_classify(clean_query)
        else:
            classification = self._classify_with_backend(clean_query)

        if classification.confidence < self.confidence_threshold:
            return QueryClassification(
                query=classification.query,
                category="multi-hop",
                confidence=classification.confidence,
                reason=classification.reason or "Low confidence fallback.",
                raw_category=classification.raw_category or classification.category,
                used_fallback=True,
            )
        return classification

    def build_prompt(self, query: str) -> str:
        """Build the few-shot classifier prompt."""

        examples = "\n".join(
            json.dumps(
                {
                    "query": example_query,
                    "category": category,
                    "confidence": confidence,
                    "reason": reason,
                }
            )
            for example_query, category, confidence, reason in FEW_SHOT_EXAMPLES
        )
        return f"""Classify the repository question into exactly one category:
- simple-lookup: asks for one symbol, file, definition, caller, callee, or direct fact.
- multi-hop: requires following calls/imports/paths or combining multiple code facts.
- exploratory: broad overview, architecture, comparison, or discovery request.

Return strict JSON with keys: category, confidence, reason.
Confidence must be a number from 0 to 1.

Examples:
{examples}

Question: {query}
JSON:"""

    def _classify_with_backend(self, query: str) -> QueryClassification:
        prompt = self.build_prompt(query)
        raw_response = self.backend.complete(prompt)
        data = self._parse_json(raw_response)
        raw_category = str(data.get("category", "multi-hop"))
        category = self._validated_category(raw_category)
        confidence = self._validated_confidence(data.get("confidence", 0.0))
        return QueryClassification(
            query=query,
            category=category,
            confidence=confidence,
            reason=str(data.get("reason", "")),
            raw_category=raw_category,
            used_fallback=category != raw_category,
        )

    def _heuristic_classify(self, query: str) -> QueryClassification:
        normalized = query.lower()
        simple_patterns = [
            r"\bwhere\s+is\b",
            r"\bdefined\b",
            r"\bdefinition\b",
            r"\bfind\s+(function|class|method|symbol)\b",
            r"\bwhat\s+(calls|imports)\b",
            r"\bshow\s+(function|class|method|symbol)\b",
            r"\bfile\s+contains\b",
        ]
        multihop_patterns = [
            r"\bhow\s+does\b.*\bflow\b",
            r"\bpath\s+between\b",
            r"\btrace\b",
            r"\bcall\s+chain\b",
            r"\bend[- ]?to[- ]?end\b",
            r"\bimpact\b",
            r"\bdependencies?\b",
            r"\bfrom\b.*\bto\b",
        ]
        exploratory_patterns = [
            r"\boverview\b",
            r"\barchitecture\b",
            r"\bexplain\b",
            r"\bwhat\s+should\s+i\s+read\b",
            r"\bcompare\b",
            r"\bsummarize\b",
            r"\bexplore\b",
            r"\bunderstand\b",
        ]

        if self._matches(normalized, multihop_patterns):
            return QueryClassification(
                query=query,
                category="multi-hop",
                confidence=0.86,
                reason="Query asks for traversal or combined code flow.",
                raw_category="multi-hop",
            )
        if self._matches(normalized, exploratory_patterns):
            return QueryClassification(
                query=query,
                category="exploratory",
                confidence=0.82,
                reason="Query asks for broad explanation or discovery.",
                raw_category="exploratory",
            )
        if self._matches(normalized, simple_patterns) or self._looks_like_identifier(
            query
        ):
            return QueryClassification(
                query=query,
                category="simple-lookup",
                confidence=0.84,
                reason="Query targets a direct symbol or file lookup.",
                raw_category="simple-lookup",
            )
        return QueryClassification(
            query=query,
            category="multi-hop",
            confidence=0.4,
            reason="No strong pattern matched.",
            raw_category="unknown",
            used_fallback=True,
        )

    def _parse_json(self, raw_response: str) -> dict[str, object]:
        try:
            return json.loads(raw_response)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", raw_response, flags=re.DOTALL)
            if match is None:
                return {}
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                return {}

    def _validated_category(self, category: str) -> QueryCategory:
        if category in VALID_CATEGORIES:
            return category  # type: ignore[return-value]
        return "multi-hop"

    def _validated_confidence(self, value: object) -> float:
        try:
            confidence = float(value)
        except (TypeError, ValueError):
            return 0.0
        return min(max(confidence, 0.0), 1.0)

    def _matches(self, query: str, patterns: list[str]) -> bool:
        return any(re.search(pattern, query) for pattern in patterns)

    def _looks_like_identifier(self, query: str) -> bool:
        stripped = query.strip("`'\" ")
        return bool(
            re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*", stripped)
        )


ExpectedAnswerType = Literal["symbol", "path", "files", "explanation", "evidence"]


@dataclass(frozen=True)
class SubQuery:
    """One ordered retrieval sub-query."""

    id: str
    text: str
    expected_answer_type: ExpectedAnswerType
    context_from: list[str]


@dataclass(frozen=True)
class SubQueryDependency:
    """Directed dependency between sub-queries."""

    source: str
    target: str
    reason: str = ""


@dataclass(frozen=True)
class QueryDecomposition:
    """Decomposition result for agentic retrieval planning."""

    query: str
    needs_decomposition: bool
    sub_queries: list[SubQuery]
    dependency_edges: list[SubQueryDependency]
    classification: QueryClassification
    repo_context_used: str = ""
    transitions: list[str] | None = None


class QueryDecompositionStateMachine:
    """LangGraph-compatible decomposition state machine with local fallback."""

    transitions = [
        "classify",
        "route",
        "decompose",
        "validate",
        "finalize",
    ]

    def __init__(self, decomposer: "QueryDecomposer") -> None:
        self.decomposer = decomposer

    def invoke(self, state: dict[str, Any]) -> dict[str, Any]:
        graph = self._build_langgraph()
        if graph is not None:
            return graph.invoke(state)
        return self._invoke_local(state)

    def _invoke_local(self, state: dict[str, Any]) -> dict[str, Any]:
        for transition in self.transitions:
            state = getattr(self, f"_{transition}")(state)
            state.setdefault("transitions", []).append(transition)
        return state

    def _build_langgraph(self) -> Any | None:
        try:
            from langgraph.graph import END, StateGraph
        except ImportError:
            return None

        graph = StateGraph(dict)
        graph.add_node("classify", self._classify)
        graph.add_node("route", self._route)
        graph.add_node("decompose", self._decompose)
        graph.add_node("validate", self._validate)
        graph.add_node("finalize", self._finalize)
        graph.set_entry_point("classify")
        graph.add_edge("classify", "route")
        graph.add_edge("route", "decompose")
        graph.add_edge("decompose", "validate")
        graph.add_edge("validate", "finalize")
        graph.add_edge("finalize", END)
        return graph.compile()

    def _classify(self, state: dict[str, Any]) -> dict[str, Any]:
        state["classification"] = self.decomposer.classifier.classify(state["query"])
        return state

    def _route(self, state: dict[str, Any]) -> dict[str, Any]:
        classification = state["classification"]
        state["needs_decomposition"] = classification.category == "multi-hop"
        return state

    def _decompose(self, state: dict[str, Any]) -> dict[str, Any]:
        if not state["needs_decomposition"]:
            state["sub_queries"] = [
                self.decomposer._single_sub_query(
                    state["query"],
                    state["classification"],
                )
            ]
            state["dependency_edges"] = []
            return state

        if self.decomposer.backend is None:
            decomposition = self.decomposer._heuristic_decomposition(
                state["query"],
                state["repo_context"],
                state["classification"],
            )
        else:
            decomposition = self.decomposer._llm_decomposition(
                state["query"],
                state["repo_context"],
                state["classification"],
            )
        state["sub_queries"] = decomposition.sub_queries
        state["dependency_edges"] = decomposition.dependency_edges
        return state

    def _validate(self, state: dict[str, Any]) -> dict[str, Any]:
        if not state["needs_decomposition"]:
            return state

        sub_queries = self.decomposer._normalize_sub_queries(state["sub_queries"])
        if len(sub_queries) < 2 or len(sub_queries) > 5:
            fallback = self.decomposer._heuristic_decomposition(
                state["query"],
                state["repo_context"],
                state["classification"],
            )
            state["sub_queries"] = fallback.sub_queries
            state["dependency_edges"] = fallback.dependency_edges
            return state

        valid_ids = {sub_query.id for sub_query in sub_queries}
        state["sub_queries"] = sub_queries
        state["dependency_edges"] = [
            edge
            for edge in self.decomposer._normalize_dependency_edges(
                state["dependency_edges"]
            )
            if edge.source in valid_ids and edge.target in valid_ids
        ]
        return state

    def _finalize(self, state: dict[str, Any]) -> dict[str, Any]:
        state["decomposition"] = QueryDecomposition(
            query=state["query"],
            needs_decomposition=state["needs_decomposition"],
            sub_queries=state["sub_queries"],
            dependency_edges=state["dependency_edges"],
            classification=state["classification"],
            repo_context_used=state["repo_context"],
            transitions=list(state.get("transitions", [])) + ["finalize"],
        )
        return state


class QueryDecomposer:
    """Decompose multi-hop questions into ordered retrieval sub-queries."""

    def __init__(
        self,
        *,
        backend: QueryClassifierBackend | None = None,
        classifier: QueryClassifier | None = None,
    ) -> None:
        self.backend = backend
        self.classifier = classifier or QueryClassifier()
        self.state_machine = QueryDecompositionStateMachine(self)

    def decompose(
        self,
        query: str,
        *,
        repo_context: str = "",
    ) -> QueryDecomposition:
        """Run the decomposition state machine."""

        state = {
            "query": query.strip(),
            "repo_context": repo_context.strip(),
            "transitions": [],
        }
        final_state = self.state_machine.invoke(state)
        return final_state["decomposition"]

    def build_decomposition_prompt(
        self,
        query: str,
        *,
        repo_context: str = "",
    ) -> str:
        """Build the LLM prompt for multi-hop decomposition."""

        return f"""Decompose the repository question into 2-5 ordered sub-queries.
Use the repository context to make sub-queries specific to available modules,
symbols, files, or graph relationships.

Each sub-query must include:
- id: q1, q2, ...
- text: the retrieval question
- expected_answer_type: one of symbol, path, files, explanation, evidence
- context_from: list of previous sub-query ids this step depends on

Also return dependency_edges as source/target pairs.
Return strict JSON with keys: needs_decomposition, sub_queries, dependency_edges.

Repository context:
{repo_context or "No repository context provided."}

Question: {query}
JSON:"""

    def _llm_decomposition(
        self,
        query: str,
        repo_context: str,
        classification: QueryClassification,
    ) -> QueryDecomposition:
        assert self.backend is not None
        raw_response = self.backend.complete(
            self.build_decomposition_prompt(query, repo_context=repo_context)
        )
        data = parse_json_object(raw_response)
        sub_queries = self._normalize_sub_queries(data.get("sub_queries", []))
        dependency_edges = self._normalize_dependency_edges(
            data.get("dependency_edges", [])
        )
        return QueryDecomposition(
            query=query,
            needs_decomposition=bool(data.get("needs_decomposition", True)),
            sub_queries=sub_queries,
            dependency_edges=dependency_edges,
            classification=classification,
            repo_context_used=repo_context,
        )

    def _heuristic_decomposition(
        self,
        query: str,
        repo_context: str,
        classification: QueryClassification,
    ) -> QueryDecomposition:
        context_hint = f" using repo context: {repo_context}" if repo_context else ""
        sub_queries = [
            SubQuery(
                id="q1",
                text=f"Identify the entry symbols and files related to: {query}{context_hint}",
                expected_answer_type="symbol",
                context_from=[],
            ),
            SubQuery(
                id="q2",
                text="Trace calls, imports, or graph paths from the q1 symbols.",
                expected_answer_type="path",
                context_from=["q1"],
            ),
            SubQuery(
                id="q3",
                text="Collect supporting code chunks and documentation for the traced flow.",
                expected_answer_type="evidence",
                context_from=["q1", "q2"],
            ),
        ]
        edges = [
            SubQueryDependency("q1", "q2", "Trace depends on identified symbols."),
            SubQueryDependency("q2", "q3", "Evidence depends on traced paths."),
        ]
        return QueryDecomposition(
            query=query,
            needs_decomposition=True,
            sub_queries=sub_queries,
            dependency_edges=edges,
            classification=classification,
            repo_context_used=repo_context,
        )

    def _single_sub_query(
        self,
        query: str,
        classification: QueryClassification,
    ) -> SubQuery:
        answer_type: ExpectedAnswerType = (
            "explanation" if classification.category == "exploratory" else "symbol"
        )
        return SubQuery(
            id="q1",
            text=query,
            expected_answer_type=answer_type,
            context_from=[],
        )

    def _normalize_sub_queries(self, raw_items: object) -> list[SubQuery]:
        if not isinstance(raw_items, list):
            return []
        sub_queries: list[SubQuery] = []
        for index, item in enumerate(raw_items, start=1):
            if isinstance(item, SubQuery):
                sub_queries.append(item)
                continue
            if not isinstance(item, dict):
                continue
            expected_type = item.get("expected_answer_type", "evidence")
            if expected_type not in {
                "symbol",
                "path",
                "files",
                "explanation",
                "evidence",
            }:
                expected_type = "evidence"
            context_from = item.get("context_from", [])
            sub_queries.append(
                SubQuery(
                    id=str(item.get("id") or f"q{index}"),
                    text=str(item.get("text") or ""),
                    expected_answer_type=expected_type,  # type: ignore[arg-type]
                    context_from=(
                        [str(value) for value in context_from if isinstance(value, str)]
                        if isinstance(context_from, list)
                        else []
                    ),
                )
            )
        return [sub_query for sub_query in sub_queries if sub_query.text]

    def _normalize_dependency_edges(
        self, raw_items: object
    ) -> list[SubQueryDependency]:
        if not isinstance(raw_items, list):
            return []
        edges: list[SubQueryDependency] = []
        for item in raw_items:
            if isinstance(item, SubQueryDependency):
                edges.append(item)
                continue
            if not isinstance(item, dict):
                continue
            source = item.get("source")
            target = item.get("target")
            if not isinstance(source, str) or not isinstance(target, str):
                continue
            edges.append(
                SubQueryDependency(
                    source=source,
                    target=target,
                    reason=str(item.get("reason", "")),
                )
            )
        return edges


def parse_json_object(raw_response: str) -> dict[str, Any]:
    """Parse strict or fenced JSON object output from an LLM."""

    try:
        return json.loads(raw_response)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw_response, flags=re.DOTALL)
        if match is None:
            return {}
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return {}
