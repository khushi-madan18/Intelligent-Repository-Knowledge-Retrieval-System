"""Tests for generated-answer evaluation."""

from __future__ import annotations

import json
from dataclasses import dataclass

from src.reporag.evaluation.generation_eval import (
    GenerationEvaluator,
    heuristic_judge,
    parse_judge_response,
)
from src.reporag.generation.context_assembler import AssembledContext, ContextChunk


@dataclass
class FakeJudgeClient:
    payload: dict[str, object]
    prompt_seen: str = ""
    model_seen: str = ""

    def judge(self, prompt: str, *, model: str) -> str:
        self.prompt_seen = prompt
        self.model_seen = model
        return json.dumps(self.payload)


def context() -> AssembledContext:
    return AssembledContext(
        text=(
            "### src/auth.py:10-18\n"
            "10: def authenticate_user(email, token):\n"
            "11:     if not token:\n"
            "12:         return False\n"
            "13:     return email.endswith('@example.com')"
        ),
        chunks=[
            ContextChunk(
                id="auth",
                file_path="src/auth.py",
                start_line=10,
                end_line=18,
                text=(
                    "def authenticate_user(email, token):\n"
                    "    if not token:\n"
                    "        return False\n"
                    "    return email.endswith('@example.com')"
                ),
            )
        ],
        token_count=20,
        truncated=False,
    )


def test_generation_evaluator_uses_configurable_judge_model() -> None:
    judge = FakeJudgeClient(
        {
            "faithfulness": 0.92,
            "answer_relevance": 0.87,
            "unsupported_claims": [],
            "notes": "grounded",
        }
    )
    evaluator = GenerationEvaluator(judge_client=judge, judge_model="judge-small")

    result = evaluator.evaluate(
        query="Where is authenticate_user defined?",
        answer="It is in src/auth.py [src/auth.py:10-18].",
        context=context(),
    )

    assert result.faithfulness == 0.92
    assert result.answer_relevance == 0.87
    assert result.hallucination_detected is False
    assert result.citation_coverage == 1.0
    assert result.judge_model == "judge-small"
    assert judge.model_seen == "judge-small"
    assert "RETRIEVED_CONTEXT" in judge.prompt_seen


def test_generation_evaluator_flags_unsupported_claims_from_judge() -> None:
    evaluator = GenerationEvaluator(
        judge_client=FakeJudgeClient(
            {
                "faithfulness": 0.2,
                "answer_relevance": 0.8,
                "unsupported_claims": [
                    {
                        "claim": "The function uses Redis sessions.",
                        "reason": "Redis is not in the provided context.",
                    }
                ],
            }
        )
    )

    result = evaluator.evaluate(
        query="How does authenticate_user work?",
        answer="It checks tokens. The function uses Redis sessions.",
        context=context(),
    )

    assert result.hallucination_detected is True
    assert result.unsupported_claims[0].claim == "The function uses Redis sessions."
    assert result.faithfulness == 0.2


def test_generation_evaluator_computes_invalid_citation_coverage() -> None:
    evaluator = GenerationEvaluator()

    result = evaluator.evaluate(
        query="Where is authenticate_user defined?",
        answer=(
            "It is in auth [src/auth.py:10-18]. "
            "It is also in a missing file [src/missing.py:1-2]."
        ),
        context=context(),
    )

    assert result.citation_coverage == 0.5
    assert [citation.valid for citation in result.citations] == [True, False]


def test_heuristic_judge_detects_unsupported_claim_without_llm() -> None:
    result = heuristic_judge(
        query="How does authenticate_user work?",
        answer="The function validates tokens. It stores sessions in Redis.",
        context=context(),
    )

    assert 0 <= result.faithfulness <= 1
    assert 0 <= result.answer_relevance <= 1
    assert result.unsupported_claims


def test_bad_judge_response_falls_back_to_heuristic_scores() -> None:
    fallback = heuristic_judge(
        query="Where is authenticate_user defined?",
        answer="It is in auth.",
        context=context(),
    )

    parsed = parse_judge_response("not-json", fallback=fallback)

    assert parsed == fallback
