"""Code-aware prompt templates for answer generation."""

from __future__ import annotations

from dataclasses import dataclass

from src.reporag.agent.planner import QueryCategory
from src.reporag.generation.context_assembler import AssembledContext, estimate_tokens

CITATION_INSTRUCTION = (
    "Cite every factual code claim with [file_path:start_line-end_line]. "
    "Use only the provided context. If the context is insufficient, say what is missing."
)

FEW_SHOT_EXAMPLES = """Few-shot examples:

Q: Where is authenticate_user defined?
A: `authenticate_user` is defined in the auth service and validates credentials before returning a token [src/auth.py:10-18].

Q: How does login reach the database?
A: The route calls `login`, `login` calls `create_session`, and `create_session` writes the session row [src/routes/auth.py:22-30] [src/services/auth.py:44-58] [src/db/session.py:12-21].
"""

COMPACT_FEW_SHOT_EXAMPLES = (
    "Example: A cited answer names the symbol and source location [src/auth.py:10-18]."
)


@dataclass(frozen=True)
class PromptRequest:
    """Prompt build request."""

    query: str
    query_type: QueryCategory
    context: AssembledContext
    max_tokens: int = 8000


@dataclass(frozen=True)
class BuiltPrompt:
    """Built prompt and metadata."""

    text: str
    query_type: QueryCategory
    token_count: int
    truncated: bool


class PromptBuilder:
    """Build code-aware answer prompts by query type."""

    def __init__(self, *, max_tokens: int = 8000) -> None:
        if max_tokens < 1:
            raise ValueError("max_tokens must be at least 1")
        self.max_tokens = max_tokens

    def build(
        self,
        query: str,
        *,
        query_type: QueryCategory,
        context: AssembledContext,
        max_tokens: int | None = None,
    ) -> BuiltPrompt:
        """Build a prompt for the query type and context window."""

        budget = max_tokens or self.max_tokens
        if budget < 1:
            raise ValueError("max_tokens must be at least 1")

        context_text = context.text
        prompt = self._format_prompt(
            query=query,
            query_type=query_type,
            context_text=context_text,
            few_shot_examples=FEW_SHOT_EXAMPLES,
        )
        truncated = context.truncated

        while estimate_tokens(prompt) > budget and context_text:
            truncated = True
            context_text = "\n".join(context_text.splitlines()[:-1])
            prompt = self._format_prompt(
                query=query,
                query_type=query_type,
                context_text=context_text,
                few_shot_examples=FEW_SHOT_EXAMPLES,
            )

        if estimate_tokens(prompt) > budget:
            truncated = True
            prompt = self._format_prompt(
                query=query,
                query_type=query_type,
                context_text=context_text,
                few_shot_examples=COMPACT_FEW_SHOT_EXAMPLES,
            )

        if estimate_tokens(prompt) > budget:
            truncated = True
            prompt = COMPACT_TEMPLATE.format(
                citation_instruction=CITATION_INSTRUCTION,
                query=query,
                context=context_text,
            )

        while estimate_tokens(prompt) > budget and context_text:
            truncated = True
            context_text = "\n".join(context_text.splitlines()[:-1])
            prompt = COMPACT_TEMPLATE.format(
                citation_instruction=CITATION_INSTRUCTION,
                query=query,
                context=context_text,
            )

        return BuiltPrompt(
            text=prompt,
            query_type=query_type,
            token_count=estimate_tokens(prompt),
            truncated=truncated,
        )

    def _format_prompt(
        self,
        *,
        query: str,
        query_type: QueryCategory,
        context_text: str,
        few_shot_examples: str,
    ) -> str:
        template = self._template_for(query_type)
        return template.format(
            citation_instruction=CITATION_INSTRUCTION,
            few_shot_examples=few_shot_examples,
            query=query,
            context=context_text,
        )

    def _template_for(self, query_type: QueryCategory) -> str:
        templates: dict[QueryCategory, str] = {
            "simple-lookup": SIMPLE_LOOKUP_TEMPLATE,
            "multi-hop": MULTI_HOP_TEMPLATE,
            "exploratory": EXPLORATORY_TEMPLATE,
        }
        return templates[query_type]


SIMPLE_LOOKUP_TEMPLATE = """You answer direct code lookup questions.

Instructions:
- Give the exact symbol, file, and line range when available.
- Keep the answer concise.
- {citation_instruction}

{few_shot_examples}

Retrieved context:
{context}

Question: {query}
Answer:"""


MULTI_HOP_TEMPLATE = """You answer multi-hop repository questions.

Instructions:
- Explain the ordered flow across files, functions, classes, or modules.
- Mention uncertainty when a link is missing from context.
- {citation_instruction}

{few_shot_examples}

Retrieved context:
{context}

Question: {query}
Answer with step-by-step reasoning grounded in citations:"""


EXPLORATORY_TEMPLATE = """You answer exploratory repository understanding questions.

Instructions:
- Summarize the main concepts first, then list important files or symbols.
- Prefer architectural explanations over isolated snippets.
- {citation_instruction}

{few_shot_examples}

Retrieved context:
{context}

Question: {query}
Answer:"""


COMPACT_TEMPLATE = """Answer using only retrieved context. {citation_instruction}

Context:
{context}

Question: {query}
Answer:"""
