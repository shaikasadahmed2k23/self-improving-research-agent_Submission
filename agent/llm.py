"""LLM factory: Groq (primary) with automatic Gemini fallback.

Tools / structured-output schemas are applied to each provider *before* wrapping in
fallbacks, because `RunnableWithFallbacks` has no `bind_tools` / `with_structured_output`.
"""
import logging
from typing import Any, Sequence

from langchain_core.messages import BaseMessage
from langchain_core.runnables import Runnable

from agent import config

# google-genai logs an "automatic function calling" notice on every call; it's noise for us.
logging.getLogger("google_genai.models").setLevel(logging.ERROR)


def is_reasoning_model(model: str) -> bool:
    return model.startswith("openai/gpt-oss")


def groq_chat(model: str, *, temperature: float = 0.2, max_tokens: int | None = None):
    """Build a ChatGroq client with safe settings for reasoning (gpt-oss) models."""
    from langchain_groq import ChatGroq

    kwargs: dict[str, Any] = {}
    if is_reasoning_model(model):
        kwargs["reasoning_effort"] = config.GROQ_REASONING_EFFORT
    return ChatGroq(
        model=model,
        api_key=config.GROQ_API_KEY,
        temperature=temperature,
        max_tokens=max_tokens or config.LLM_MAX_TOKENS,
        max_retries=2,
        **kwargs,
    )


def gemini_chat(*, temperature: float = 0.2, max_tokens: int | None = None):
    from langchain_google_genai import ChatGoogleGenerativeAI

    return ChatGoogleGenerativeAI(
        model=config.GEMINI_MODEL,
        google_api_key=config.GOOGLE_API_KEY,
        temperature=temperature,
        max_output_tokens=max_tokens or config.LLM_MAX_TOKENS,
        max_retries=2,
    )


def get_llm(
    role: str,
    *,
    tools: Sequence[Any] | None = None,
    schema: Any | None = None,
    temperature: float = 0.2,
    max_tokens: int | None = None,
) -> Runnable:
    """Return a runnable for a node role (planner, executor, writer, critic, ...).

    Fallback order: the role's Groq model -> other Groq models (separate daily quotas) -> Gemini.
    """

    def prepare(llm, reasoning_model: bool = False):
        if tools:
            llm = llm.bind_tools(list(tools))
        if schema is not None:
            # gpt-oss function-calling output sometimes has invalid JSON escapes (e.g. \'); Groq's strict
            # JSON-schema mode is constrained decoding and avoids that.
            if reasoning_model:
                llm = llm.with_structured_output(schema, method="json_schema", strict=True)
            else:
                llm = llm.with_structured_output(schema)
        return llm

    candidates = []
    if config.GROQ_API_KEY:
        primary_model = config.groq_model_for(role)
        models = [primary_model] + [m for m in config.GROQ_FALLBACK_MODELS if m != primary_model]
        for model in dict.fromkeys(models):
            llm = groq_chat(model, temperature=temperature, max_tokens=max_tokens)
            candidates.append(prepare(llm, is_reasoning_model(model)))
    if config.GOOGLE_API_KEY:
        candidates.append(prepare(gemini_chat(temperature=temperature, max_tokens=max_tokens)))
    if not candidates:
        raise RuntimeError("No LLM configured: set GROQ_API_KEY and/or GOOGLE_API_KEY in .env")

    primary, *fallbacks = candidates
    return primary.with_fallbacks(fallbacks) if fallbacks else primary


def text_of(message: BaseMessage) -> str:
    """Plain-text content of a chat message (Gemini may return content blocks)."""
    return (message.text or "").strip()
