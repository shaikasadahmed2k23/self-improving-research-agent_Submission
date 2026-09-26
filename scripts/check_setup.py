"""Verify .env keys and connectivity for every external service the agent uses.

Usage:  python scripts/check_setup.py
Exit code 0 when the minimum set works (one LLM + one search provider).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent import config  # noqa: E402
from agent.llm import gemini_chat, groq_chat, nvidia_chat, text_of  # noqa: E402

PING = "Reply with exactly one word: OK"


def check_groq() -> str:
    if not config.GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY is empty")

    models = {config.GROQ_MODEL}
    if config.USE_STRONG_MODEL:
        models.add(config.GROQ_MODEL_STRONG)
    replies = []
    for model in sorted(models):
        # Same client settings as the agent (reasoning_effort + a budget that covers reasoning).
        reply = text_of(groq_chat(model, temperature=0, max_tokens=512).invoke(PING))
        if not reply:
            raise RuntimeError(f"{model} returned empty content (reasoning used the whole token budget?)")
        replies.append(f"{model} -> {reply[:20]!r}")
    return "; ".join(replies)


def check_gemini() -> str:
    if not config.GOOGLE_API_KEY:
        raise RuntimeError("GOOGLE_API_KEY is empty")
    reply = text_of(gemini_chat(temperature=0, max_tokens=512).invoke(PING))
    if not reply:
        raise RuntimeError(f"{config.GEMINI_MODEL} returned empty content")
    return f"{config.GEMINI_MODEL} -> {reply[:20]!r}"


def check_nvidia() -> str:
    if not config.NVIDIA_API_KEY:
        raise RuntimeError("NVIDIA_API_KEY is empty")
    reply = text_of(nvidia_chat(temperature=0, max_tokens=512).invoke(PING))
    if not reply:
        raise RuntimeError(f"{config.NVIDIA_MODEL} returned empty content")
    return f"{config.NVIDIA_MODEL} -> {reply[:20]!r}"


def check_tavily() -> str:
    if not config.TAVILY_API_KEY:
        raise RuntimeError("TAVILY_API_KEY is empty")
    from tavily import TavilyClient

    res = TavilyClient(api_key=config.TAVILY_API_KEY).search("LangGraph", max_results=1)
    return f"{len(res.get('results', []))} result(s), e.g. {res['results'][0]['url']}"


def check_ddg() -> str:
    from ddgs import DDGS

    res = list(DDGS().text("LangGraph", max_results=1))
    return f"{len(res)} result(s), e.g. {res[0]['href']}" if res else "0 results"


def main() -> int:
    checks = [
        ("Groq (primary LLM)", check_groq),
        ("NVIDIA NIM (fallback LLM)", check_nvidia),
        ("Gemini (fallback LLM)", check_gemini),
        ("Tavily (primary search)", check_tavily),
        ("DuckDuckGo (fallback search)", check_ddg),
    ]
    ok = {}
    print(f"Strong model mode: {'ON' if config.USE_STRONG_MODEL else f'OFF (dev, {config.GROQ_MODEL})'}\n")
    for name, fn in checks:
        try:
            detail = fn()
            ok[name] = True
            print(f"[PASS] {name}: {detail}")
        except Exception as exc:  # report every failure, keep going
            ok[name] = False
            print(f"[FAIL] {name}: {type(exc).__name__}: {str(exc)[:200]}")

    llm_ok = ok["Groq (primary LLM)"] or ok["NVIDIA NIM (fallback LLM)"] or ok["Gemini (fallback LLM)"]
    search_ok = ok["Tavily (primary search)"] or ok["DuckDuckGo (fallback search)"]
    print()
    if llm_ok and search_ok:
        print("Setup OK: at least one LLM and one search provider work.")
        if not all(ok.values()):
            print("Note: some fallbacks are unavailable; the agent will run with reduced resilience.")
        return 0
    print("Setup INCOMPLETE: need at least one working LLM and one working search provider.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
