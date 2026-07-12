"""Tests for code-aware prompt builder."""

from src.reporag.generation.context_assembler import AssembledContext
from src.reporag.generation.prompt_builder import (
    CITATION_INSTRUCTION,
    FEW_SHOT_EXAMPLES,
    PromptBuilder,
)


def context(
    text: str = "### src/auth.py:10-12\n10: def login():\n11:     return token",
) -> AssembledContext:
    return AssembledContext(
        text=text,
        chunks=[],
        token_count=len(text.split()),
        truncated=False,
    )


def test_simple_lookup_template_includes_lookup_instructions() -> None:
    prompt = PromptBuilder(max_tokens=500).build(
        "Where is login defined?",
        query_type="simple-lookup",
        context=context(),
    )

    assert "direct code lookup" in prompt.text
    assert "Where is login defined?" in prompt.text
    assert "### src/auth.py:10-12" in prompt.text
    assert prompt.query_type == "simple-lookup"


def test_multi_hop_template_includes_flow_instructions() -> None:
    prompt = PromptBuilder(max_tokens=500).build(
        "How does login reach the database?",
        query_type="multi-hop",
        context=context(),
    )

    assert "ordered flow" in prompt.text
    assert "step-by-step" in prompt.text
    assert prompt.query_type == "multi-hop"


def test_exploratory_template_includes_architecture_instructions() -> None:
    prompt = PromptBuilder(max_tokens=500).build(
        "Explain authentication architecture",
        query_type="exploratory",
        context=context(),
    )

    assert "exploratory repository" in prompt.text
    assert "architectural explanations" in prompt.text
    assert prompt.query_type == "exploratory"


def test_citation_format_is_clearly_instructed() -> None:
    prompt = PromptBuilder(max_tokens=500).build(
        "Where is login defined?",
        query_type="simple-lookup",
        context=context(),
    )

    assert CITATION_INSTRUCTION in prompt.text
    assert "[file_path:start_line-end_line]" in prompt.text


def test_few_shot_examples_are_included() -> None:
    prompt = PromptBuilder(max_tokens=500).build(
        "Where is login defined?",
        query_type="simple-lookup",
        context=context(),
    )

    assert FEW_SHOT_EXAMPLES in prompt.text
    assert "[src/auth.py:10-18]" in prompt.text


def test_prompt_fits_within_model_context_window() -> None:
    large_context = "\n".join(
        f"{line}: token token token token" for line in range(1, 200)
    )

    prompt = PromptBuilder(max_tokens=80).build(
        "Explain the code",
        query_type="exploratory",
        context=context(large_context),
    )

    assert prompt.token_count <= 80
    assert prompt.truncated is True


def test_invalid_max_tokens_raises() -> None:
    try:
        PromptBuilder(max_tokens=0)
    except ValueError as exc:
        assert "max_tokens" in str(exc)
    else:
        raise AssertionError("Expected invalid max_tokens to fail")
