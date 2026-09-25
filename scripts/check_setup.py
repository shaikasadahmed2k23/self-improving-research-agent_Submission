"""Verify .env keys and connectivity for every external service the agent uses.

Usage:  python scripts/check_setup.py
Exit code 0 when the minimum set works (one LLM + one search provider).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent import config  # noqa: E402

PING = "Reply with exactly one word: OK"


def check_groq() -> str:
    if not config.GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY is empty")
    from langchain_groq import ChatGroq

    models = {config.GROQ_MODEL}
    if config.USE_STRONG_MODEL:
        models.add(config.GROQ_MODEL_STRONG)
    replies = []
    for model in sorted(models):
        llm = ChatGroq(model=model, api_key=config.GROQ_API_KEY, temperature=0, max_tokens=5)
        replies.append(f"{model} -> {llm.invoke(PING).content.strip()!r}")
    return "; ".join(replies)


def check_gemini() -> str:
    if not config.GOOGLE_API_KEY:
        raise RuntimeError("GOOGLE_API_KEY is empty")
    from langchain_google_genai import ChatGoogleGenerativeAI

    llm = ChatGoogleGenerativeAI(
        model=config.GEMINI_MODEL, google_api_key=config.GOOGLE_API_KEY, temperature=0
    )
    return f"{config.GEMINI_MODEL} -> {llm.invoke(PING).content.strip()[:20]!r}"


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
        ("Gemini (fallback LLM)", check_gemini),
        ("Tavily (primary search)", check_tavily),
        ("DuckDuckGo (fallback search)", check_ddg),
    ]
    ok = {}
    print(f"Strong model mode: {'ON' if config.USE_STRONG_MODEL else 'OFF (dev, 8B)'}\n")
    for name, fn in checks:
        try:
            detail = fn()
            ok[name] = True
            print(f"[PASS] {name}: {detail}")
        except Exception as exc:  # report every failure, keep going
            ok[name] = False
            print(f"[FAIL] {name}: {type(exc).__name__}: {str(exc)[:200]}")

    llm_ok = ok["Groq (primary LLM)"] or ok["Gemini (fallback LLM)"]
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
