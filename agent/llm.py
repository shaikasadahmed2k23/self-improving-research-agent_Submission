"""LLM factory: Groq (primary) -> NVIDIA NIM -> Gemini fallbacks.

Tools / structured-output schemas are applied to each provider *before* wrapping in
fallbacks, because `RunnableWithFallbacks` has no `bind_tools` / `with_structured_output`.
"""
import json
import logging
import re
from typing import Any, Sequence

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage, convert_to_messages
from langchain_core.runnables import Runnable, RunnableLambda
from pydantic import ValidationError

from agent import config

# google-genai logs an "automatic function calling" notice on every call; it's noise for us.
logging.getLogger("google_genai.models").setLevel(logging.ERROR)


def is_reasoning_model(model: str) -> bool:
    return model.startswith("openai/gpt-oss")


def uses_strict_schema(model: str) -> bool:
    """Models whose structured output goes through Groq's strict json_schema mode. Groq enforces it for gpt-oss only:
    qwen3.8 ignored the schema (invented keys like ".lessons"), which pydantic silently turned into empty defaults.
    Other models use function calling, whose arguments Groq validates against the schema."""
    return is_reasoning_model(model)


def groq_chat(model: str, *, temperature: float = 0.2, max_tokens: int | None = None):
    """Build a ChatGroq client with safe settings for reasoning (gpt-oss) models."""
    from langchain_groq import ChatGroq

    kwargs: dict[str, Any] = {}
    if is_reasoning_model(model):
        kwargs["reasoning_effort"] = config.GROQ_REASONING_EFFORT
    elif model.startswith("qwen/"):
        # qwen3 thinks by default; with the 1000-token output cap the thinking alone hit the limit (finish_reason=length)
        kwargs["reasoning_effort"] = "none"
    cap = config.GROQ_MAX_TOKENS_CAP.get(model)
    budget = max_tokens or config.LLM_MAX_TOKENS
    return ChatGroq(
        model=model,
        api_key=config.GROQ_API_KEY,
        temperature=temperature,
        max_tokens=min(budget, cap) if cap else budget,
        # capped models hit their per-minute output limit often; Groq's 429 carries a short retry-after, so wait it out
        max_retries=6 if cap else 2,
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


def nvidia_chat(*, temperature: float = 0.2, max_tokens: int | None = None):
    """NVIDIA NIM (OpenAI-compatible API, free for development use)."""
    from langchain_openai import ChatOpenAI

    kwargs: dict[str, Any] = {}
    if is_reasoning_model(config.NVIDIA_MODEL):
        kwargs["reasoning_effort"] = config.GROQ_REASONING_EFFORT
    return ChatOpenAI(
        model=config.NVIDIA_MODEL,
        base_url=config.NVIDIA_BASE_URL,
        api_key=config.NVIDIA_API_KEY,
        temperature=temperature,
        max_tokens=max_tokens or config.LLM_MAX_TOKENS,
        max_retries=2,
        timeout=120,
        **kwargs,
    )


def _json_text(text: str) -> str:
    """Strip a ```json fence if the model added one."""
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    return (m.group(1) if m else text).strip()


def json_mode_structured(llm, schema) -> Runnable:
    """Structured output for endpoints without strict json_schema support: JSON mode + the schema in the
    prompt, pydantic validation, and one retry that shows the model its validation error."""
    json_llm = llm.bind(response_format={"type": "json_object"})
    instruction = "Reply with only a JSON object that matches this JSON schema:\n" + json.dumps(schema.model_json_schema())

    def run(messages, config):
        msgs = [HumanMessage(messages)] if isinstance(messages, str) else convert_to_messages(messages)
        if msgs and isinstance(msgs[0], SystemMessage):
            msgs = [SystemMessage(f"{msgs[0].text}\n\n{instruction}"), *msgs[1:]]
        else:
            msgs = [SystemMessage(instruction), *msgs]
        for attempt in range(2):
            reply = json_llm.invoke(msgs, config=config)
            try:
                return schema.model_validate_json(_json_text(text_of(reply)))
            except ValidationError as exc:
                if attempt:
                    raise
                msgs = [*msgs, reply, HumanMessage(f"That JSON is invalid:\n{exc}\nReply with only the corrected JSON object.")]

    return RunnableLambda(run)


def get_llm(
    role: str,
    *,
    tools: Sequence[Any] | None = None,
    schema: Any | None = None,
    temperature: float = 0.2,
    max_tokens: int | None = None,
) -> Runnable:
    """Return a runnable for a node role (planner, executor, writer, critic, ...).

    Fallback order: the role's Groq model -> other Groq models (separate daily quotas) -> NVIDIA NIM -> Gemini.
    """

    def prepare(llm, strict_schema: bool = False, json_mode: bool = False):
        if tools:
            llm = llm.bind_tools(list(tools))
        if schema is not None and json_mode:
            llm = json_mode_structured(llm, schema)
        elif schema is not None:
            # gpt-oss function-calling output sometimes has invalid JSON escapes (e.g. \'); Groq's strict
            # JSON-schema mode is constrained decoding and avoids that.
            if strict_schema:
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
            candidates.append(prepare(llm, uses_strict_schema(model)))
    if config.NVIDIA_API_KEY:
        candidates.append(prepare(nvidia_chat(temperature=temperature, max_tokens=max_tokens), json_mode=True))
    if config.GOOGLE_API_KEY:
        candidates.append(prepare(gemini_chat(temperature=temperature, max_tokens=max_tokens)))
    if not candidates:
        raise RuntimeError("No LLM configured: set GROQ_API_KEY and/or GOOGLE_API_KEY in .env")

    primary, *fallbacks = candidates
    return primary.with_fallbacks(fallbacks) if fallbacks and config.LLM_FALLBACKS else primary


def text_of(message: BaseMessage) -> str:
    """Plain-text content of a chat message (Gemini may return content blocks)."""
    return (message.text or "").strip()
