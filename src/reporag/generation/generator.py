"""LLM answer generation with structured citation validation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from src.reporag.agent.planner import QueryCategory
from src.reporag.config import settings
from src.reporag.generation.citation import (
    Citation,
    citation_coverage,
    extract_and_validate_citations,
)
from src.reporag.generation.context_assembler import AssembledContext
from src.reporag.generation.prompt_builder import BuiltPrompt, PromptBuilder


class LLMClient(Protocol):
    """Minimal LLM client interface used by AnswerGenerator."""

    def generate(self, prompt: str) -> str:
        """Return generated answer text for a prompt."""


@dataclass(frozen=True)
class GenerationResult:
    """Structured generation output."""

    answer: str
    citations: list[Citation]
    citation_coverage: float
    prompt: BuiltPrompt
    raw_answer: str = ""
    error: str | None = None


class OpenAILLMClient:
    """OpenAI chat-completions client."""

    def __init__(
        self,
        *,
        model: str | None = None,
        api_key: str | None = None,
    ) -> None:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("Install openai to use OpenAILLMClient") from exc

        key = api_key or settings.openai_api_key.get_secret_value()
        self.model = model or settings.llm_model
        self.client = OpenAI(api_key=key)

    def generate(self, prompt: str) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": "Answer repository questions using only cited context.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0,
        )
        return response.choices[0].message.content or ""


class AnthropicLLMClient:
    """Anthropic messages client."""

    def __init__(
        self,
        *,
        model: str | None = None,
        api_key: str | None = None,
    ) -> None:
        try:
            from anthropic import Anthropic
        except ImportError as exc:
            raise RuntimeError("Install anthropic to use AnthropicLLMClient") from exc

        configured_key = (
            settings.anthropic_api_key.get_secret_value()
            if settings.anthropic_api_key is not None
            else None
        )
        self.model = model or settings.llm_model
        self.client = Anthropic(api_key=api_key or configured_key)

    def generate(self, prompt: str) -> str:
        response = self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            temperature=0,
            system="Answer repository questions using only cited context.",
            messages=[{"role": "user", "content": prompt}],
        )
        parts: list[str] = []
        for block in response.content:
            text = getattr(block, "text", None)
            if text:
                parts.append(text)
        return "\n".join(parts)


class AnswerGenerator:
    """Generate answers and validate line-level citations."""

    def __init__(
        self,
        *,
        llm_client: LLMClient | None = None,
        prompt_builder: PromptBuilder | None = None,
    ) -> None:
        self.llm_client = llm_client or default_llm_client()
        self.prompt_builder = prompt_builder or PromptBuilder()

    def generate(
        self,
        query: str,
        *,
        query_type: QueryCategory,
        context: AssembledContext,
    ) -> GenerationResult:
        """Generate a cited answer from retrieved context."""

        prompt = self.prompt_builder.build(
            query,
            query_type=query_type,
            context=context,
        )
        try:
            answer = self.llm_client.generate(prompt.text)
        except (
            Exception
        ) as exc:  # noqa: BLE001 - LLM SDKs raise provider-specific errors.
            return GenerationResult(
                answer="",
                citations=[],
                citation_coverage=0.0,
                prompt=prompt,
                raw_answer="",
                error=str(exc),
            )

        citations = extract_and_validate_citations(answer, context)
        return GenerationResult(
            answer=answer,
            citations=citations,
            citation_coverage=citation_coverage(citations),
            prompt=prompt,
            raw_answer=answer,
            error=None,
        )


def default_llm_client() -> LLMClient:
    """Create the configured provider client."""

    if settings.llm_provider == "anthropic":
        return AnthropicLLMClient()
    return OpenAILLMClient()
