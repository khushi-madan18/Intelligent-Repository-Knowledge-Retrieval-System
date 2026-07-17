"""Generation evaluation for grounded repository answers."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Protocol

from src.reporag.generation.citation import (
    Citation,
    citation_coverage,
    extract_and_validate_citations,
)
from src.reporag.generation.context_assembler import AssembledContext


class JudgeClient(Protocol):
    """Minimal LLM-as-judge interface."""

    def judge(self, prompt: str, *, model: str) -> str:
        """Return a JSON judge response for the evaluation prompt."""


@dataclass(frozen=True)
class UnsupportedClaim:
    """A generated claim that is not grounded in retrieved context."""

    claim: str
    reason: str


@dataclass(frozen=True)
class GenerationEvaluation:
    """Evaluation scores for one generated answer."""

    query: str
    answer: str
    faithfulness: float
    answer_relevance: float
    hallucination_detected: bool
    unsupported_claims: list[UnsupportedClaim]
    citation_coverage: float
    citations: list[Citation]
    judge_model: str
    judge_notes: str = ""
    raw_judge_response: str = ""


@dataclass(frozen=True)
class JudgePrompt:
    """Structured prompt sent to the judge model."""

    query: str
    answer: str
    context: str

    def render(self) -> str:
        """Render a strict JSON-scoring prompt."""

        return (
            "You are evaluating a repository RAG answer.\n"
            "Return only JSON with keys: faithfulness, answer_relevance, "
            "unsupported_claims, notes.\n"
            "Scores must be numbers from 0 to 1. unsupported_claims must be "
            "a list of objects with claim and reason.\n\n"
            f"QUERY:\n{self.query}\n\n"
            f"RETRIEVED_CONTEXT:\n{self.context}\n\n"
            f"ANSWER:\n{self.answer}\n"
        )


class GenerationEvaluator:
    """Evaluate generated answers for grounding, relevance, and citations."""

    def __init__(
        self,
        *,
        judge_client: JudgeClient | None = None,
        judge_model: str = "gpt-4o-mini",
    ) -> None:
        self.judge_client = judge_client
        self.judge_model = judge_model

    def evaluate(
        self,
        *,
        query: str,
        answer: str,
        context: AssembledContext,
    ) -> GenerationEvaluation:
        """Compute faithfulness, relevance, hallucination, and citation coverage."""

        citations = extract_and_validate_citations(answer, context)
        fallback = heuristic_judge(query=query, answer=answer, context=context)
        raw_response = ""
        judge_payload = fallback

        if self.judge_client is not None:
            prompt = JudgePrompt(
                query=query,
                answer=answer,
                context=context.text,
            ).render()
            raw_response = self.judge_client.judge(prompt, model=self.judge_model)
            judge_payload = parse_judge_response(raw_response, fallback=fallback)

        unsupported_claims = [
            UnsupportedClaim(
                claim=str(item.get("claim", "")),
                reason=str(item.get("reason", "unsupported by retrieved context")),
            )
            for item in judge_payload.unsupported_claims
            if item.get("claim")
        ]

        return GenerationEvaluation(
            query=query,
            answer=answer,
            faithfulness=clamp_score(judge_payload.faithfulness),
            answer_relevance=clamp_score(judge_payload.answer_relevance),
            hallucination_detected=bool(unsupported_claims),
            unsupported_claims=unsupported_claims,
            citation_coverage=citation_coverage(citations),
            citations=citations,
            judge_model=self.judge_model,
            judge_notes=judge_payload.notes,
            raw_judge_response=raw_response,
        )


@dataclass(frozen=True)
class _JudgePayload:
    faithfulness: float
    answer_relevance: float
    unsupported_claims: list[dict[str, str]] = field(default_factory=list)
    notes: str = ""


def parse_judge_response(response: str, *, fallback: _JudgePayload) -> _JudgePayload:
    """Parse the JSON returned by an LLM judge, falling back on bad output."""

    try:
        payload = json.loads(response)
    except json.JSONDecodeError:
        return fallback

    if not isinstance(payload, dict):
        return fallback

    unsupported = payload.get("unsupported_claims", [])
    if not isinstance(unsupported, list):
        unsupported = []

    return _JudgePayload(
        faithfulness=float(payload.get("faithfulness", fallback.faithfulness)),
        answer_relevance=float(
            payload.get("answer_relevance", fallback.answer_relevance)
        ),
        unsupported_claims=[
            item
            for item in unsupported
            if isinstance(item, dict) and isinstance(item.get("claim"), str)
        ],
        notes=str(payload.get("notes", fallback.notes)),
    )


def heuristic_judge(
    *,
    query: str,
    answer: str,
    context: AssembledContext,
) -> _JudgePayload:
    """Offline deterministic judge used when no LLM judge is configured."""

    context_terms = meaningful_terms(context.text)
    query_terms = meaningful_terms(query)
    answer_terms = meaningful_terms(answer)
    answer_claims = split_claims(answer)

    unsupported: list[dict[str, str]] = []
    for claim in answer_claims:
        claim_terms = meaningful_terms(claim)
        if not claim_terms:
            continue
        overlap = claim_terms & context_terms
        has_valid_citation = any(
            citation.valid
            for citation in extract_and_validate_citations(claim, context)
        )
        if not overlap and not has_valid_citation:
            unsupported.append(
                {
                    "claim": claim,
                    "reason": "claim terms do not appear in retrieved context",
                }
            )

    faithfulness = (
        1.0 if not answer_claims else 1.0 - (len(unsupported) / len(answer_claims))
    )
    relevance = 0.0
    if query_terms and answer_terms:
        relevance = len(query_terms & answer_terms) / len(query_terms)

    return _JudgePayload(
        faithfulness=clamp_score(faithfulness),
        answer_relevance=clamp_score(relevance),
        unsupported_claims=unsupported,
        notes="heuristic offline judge",
    )


def split_claims(answer: str) -> list[str]:
    """Split generated prose into simple claim-like sentences."""

    cleaned = re.sub(r"\[[^\[\]]+?:\d+-\d+\]", "", answer)
    return [
        part.strip() for part in re.split(r"(?<=[.!?])\s+", cleaned) if part.strip()
    ]


def meaningful_terms(text: str) -> set[str]:
    """Return normalized terms useful for rough semantic overlap."""

    stopwords = {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "for",
        "from",
        "how",
        "in",
        "is",
        "it",
        "of",
        "on",
        "or",
        "the",
        "this",
        "to",
        "where",
        "with",
    }
    return {
        token.lower()
        for token in re.findall(r"[A-Za-z_][A-Za-z0-9_]+", text)
        if token.lower() not in stopwords and len(token) > 2
    }


def clamp_score(value: float) -> float:
    """Clamp judge scores into the required 0-1 range."""

    return min(1.0, max(0.0, value))
