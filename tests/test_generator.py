"""Tests for LLM answer generation."""

from dataclasses import dataclass

from src.reporag.generation.context_assembler import AssembledContext, ContextChunk
from src.reporag.generation.generator import AnswerGenerator


@dataclass
class FakeLLMClient:
    answer: str
    prompt_seen: str = ""

    def generate(self, prompt: str) -> str:
        self.prompt_seen = prompt
        return self.answer


class FailingLLMClient:
    def generate(self, prompt: str) -> str:
        raise RuntimeError("provider unavailable")


def context() -> AssembledContext:
    return AssembledContext(
        text="### src/auth.py:10-18\n10: def authenticate_user():\n11:     return token",
        chunks=[
            ContextChunk(
                id="auth",
                file_path="src/auth.py",
                start_line=10,
                end_line=18,
                text="def authenticate_user():\n    return token",
            )
        ],
        token_count=8,
        truncated=False,
    )


def test_generator_calls_configurable_llm_client() -> None:
    client = FakeLLMClient("It is defined in the auth module [src/auth.py:10-18].")
    generator = AnswerGenerator(llm_client=client)

    result = generator.generate(
        "Where is authenticate_user defined?",
        query_type="simple-lookup",
        context=context(),
    )

    assert "Where is authenticate_user defined?" in client.prompt_seen
    assert result.answer == client.answer
    assert result.error is None


def test_generator_extracts_and_validates_citations() -> None:
    generator = AnswerGenerator(
        llm_client=FakeLLMClient("The function is available here [src/auth.py:10-18].")
    )

    result = generator.generate(
        "Where is authenticate_user defined?",
        query_type="simple-lookup",
        context=context(),
    )

    assert len(result.citations) == 1
    assert result.citations[0].valid is True
    assert result.citation_coverage == 1.0


def test_generator_flags_invalid_citations() -> None:
    generator = AnswerGenerator(
        llm_client=FakeLLMClient("This cites missing code [src/missing.py:1-2].")
    )

    result = generator.generate(
        "Where is authenticate_user defined?",
        query_type="simple-lookup",
        context=context(),
    )

    assert result.citations[0].valid is False
    assert result.citation_coverage == 0.0


def test_generator_handles_llm_errors_gracefully() -> None:
    generator = AnswerGenerator(llm_client=FailingLLMClient())

    result = generator.generate(
        "Where is authenticate_user defined?",
        query_type="simple-lookup",
        context=context(),
    )

    assert result.answer == ""
    assert result.citations == []
    assert result.citation_coverage == 0.0
    assert result.error == "provider unavailable"
