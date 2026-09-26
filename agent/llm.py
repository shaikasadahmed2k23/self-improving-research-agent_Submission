"""LLM factory: Groq (primary) -> NVIDIA NIM -> Gemini fallbacks.

Tools / structured-output schemas are applied to each provider *before* wrapping in
fallbacks, because `RunnableWithFallbacks` has no `bind_tools` / `with_structured_output`.
"""
import json
import logging
import random
import re
import time
from typing import Any, Sequence

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage, convert_to_messages
from langchain_core.runnables import Runnable, RunnableLambda
from pydantic import ValidationError

from agent import config

# google-genai logs an "automatic function calling" notice on every call; it's noise for us.
logging.getLogger("google_genai.models").setLevel(logging.ERROR)
log = logging.getLogger(__name__)


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
        max_retries=1,  # rate limits are retried by with_rate_limit_retry; this covers connection errors
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


_TRY_AGAIN = re.compile(r"try again in\s+(?:(\d+)h)?(?:(\d+)m)?(?:([\d.]+)s)?", re.I)
_RETRY_DELAY = re.compile(r"retry_?delay\W+(\d+(?:\.\d+)?)s", re.I)


def is_rate_limit(exc: BaseException) -> bool:
    """429 / quota errors from Groq, NIM (OpenAI SDK) or Gemini."""
    status = getattr(exc, "status_code", None) or getattr(getattr(exc, "response", None), "status_code", None)
    text = str(exc).lower()
    return status == 429 or any(s in text for s in ("rate limit", "rate_limit", "resource_exhausted", "quota"))


def retry_after(exc: BaseException) -> float | None:
    """Seconds the provider asks us to wait: Retry-After header, Groq's "try again in 1m2.5s", Gemini's retryDelay."""
    headers = getattr(getattr(exc, "response", None), "headers", None) or {}
    try:
        if headers.get("retry-after"):
            return float(headers["retry-after"])
    except (TypeError, ValueError):
        pass
    text = str(exc)
    m = _TRY_AGAIN.search(text)
    if m and any(m.groups()):
        h, mins, secs = (float(g) if g else 0.0 for g in m.groups())
        return h * 3600 + mins * 60 + secs
    m = _RETRY_DELAY.search(text)
    return float(m.group(1)) if m else None


def with_rate_limit_retry(runnable: Runnable) -> Runnable:
    """Wait out short rate limits (per-minute token/request caps) on the same model, with exponential backoff when the
    provider gives no wait time. Long waits (daily quota) are re-raised at once so the fallback chain moves on."""
    retries, max_wait = config.LLM_RATE_RETRIES, config.LLM_MAX_WAIT

    def run(value, config):
        for attempt in range(retries + 1):
            try:
                return runnable.invoke(value, config=config)
            except Exception as exc:
                if not is_rate_limit(exc) or attempt == retries:
                    raise
                wait = retry_after(exc)
                wait = min(2.0 * 2**attempt, max_wait) if wait is None else wait
                if wait > max_wait:
                    raise
                log.warning("Rate limited (attempt %d/%d); retrying in %.1fs: %s", attempt + 1, retries, wait, str(exc)[:120])
                time.sleep(wait + random.uniform(0, 0.5))

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

    candidates = [with_rate_limit_retry(c) for c in candidates]
    primary, *fallbacks = candidates
    return primary.with_fallbacks(fallbacks) if fallbacks and config.LLM_FALLBACKS else primary


def text_of(message: BaseMessage) -> str:
    """Plain-text content of a chat message (Gemini may return content blocks)."""
    return (message.text or "").strip()
