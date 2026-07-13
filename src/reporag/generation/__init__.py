"""Answer generation package."""

from src.reporag.generation.citation import (
    Citation,
    citation_coverage,
    extract_and_validate_citations,
    extract_citations,
    validate_citations,
)
from src.reporag.generation.context_assembler import (
    AssembledContext,
    ContextAssembler,
    ContextChunk,
    estimate_tokens,
)
from src.reporag.generation.generator import (
    AnswerGenerator,
    AnthropicLLMClient,
    GenerationResult,
    LLMClient,
    OpenAILLMClient,
    default_llm_client,
)
from src.reporag.generation.prompt_builder import (
    CITATION_INSTRUCTION,
    FEW_SHOT_EXAMPLES,
    BuiltPrompt,
    PromptBuilder,
    PromptRequest,
)

__all__ = [
    "AssembledContext",
    "AnswerGenerator",
    "AnthropicLLMClient",
    "BuiltPrompt",
    "CITATION_INSTRUCTION",
    "Citation",
    "ContextAssembler",
    "ContextChunk",
    "FEW_SHOT_EXAMPLES",
    "GenerationResult",
    "LLMClient",
    "OpenAILLMClient",
    "PromptBuilder",
    "PromptRequest",
    "citation_coverage",
    "default_llm_client",
    "estimate_tokens",
    "extract_and_validate_citations",
    "extract_citations",
    "validate_citations",
]
