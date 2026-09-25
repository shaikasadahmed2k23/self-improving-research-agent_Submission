"""Web search: Tavily first, DuckDuckGo as a keyless fallback."""
import logging

from agent import config

log = logging.getLogger(__name__)
SNIPPET_CHARS = 800


def _tavily(query: str, max_results: int) -> list[dict]:
    from tavily import TavilyClient

    res = TavilyClient(api_key=config.TAVILY_API_KEY).search(query, max_results=max_results)
    return [
        {"title": r.get("title", ""), "url": r["url"], "content": r.get("content", ""), "provider": "tavily"}
        for r in res.get("results", [])
    ]


def _ddg(query: str, max_results: int) -> list[dict]:
    from ddgs import DDGS

    return [
        {"title": r.get("title", ""), "url": r["href"], "content": r.get("body", ""), "provider": "duckduckgo"}
        for r in DDGS().text(query, max_results=max_results)
    ]


def web_search(query: str, max_results: int = 5) -> list[dict]:
    """Return [{title, url, content, provider}]. Never raises; returns [] if all providers fail."""
    providers = ([_tavily] if config.TAVILY_API_KEY else []) + [_ddg]
    for provider in providers:
        try:
            results = provider(query, max_results)
        except Exception as exc:
            log.warning("%s search failed for %r: %s", provider.__name__, query, exc)
            continue
        if results:
            for r in results:
                r["content"] = (r["content"] or "")[:SNIPPET_CHARS]
            return results
    return []
