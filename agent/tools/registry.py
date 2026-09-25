"""LLM-facing tool schemas and the dispatcher the tools node uses.

Schemas are pydantic models (class name = tool name, docstring = description), so the
LLM sees clean signatures while execution stays in our own node. That lets tool results
be registered as numbered citation sources in the shared state.
"""
from urllib.parse import parse_qsl, urlencode, urlsplit

from pydantic import BaseModel, Field

from agent.tools.calculator import calculate
from agent.tools.fetch import fetch_page as _fetch_page
from agent.tools.fetch import page_view
from agent.tools.search import web_search as _web_search


class web_search(BaseModel):
    """Search the web. Returns numbered results (title, URL, snippet). Cite results by their [number]."""

    query: str = Field(description="Focused search query, 3-10 words, using concrete names (no placeholders)")


class fetch_page(BaseModel):
    """Read the main text of a web page (e.g. an official pricing page) when snippets are not detailed enough.
    JavaScript-rendered content (like pricing tables) is included."""

    url: str = Field(description="Full http(s) URL, usually one returned by web_search")
    focus: str | None = Field(
        default=None,
        description="Optional keywords (e.g. 'storage GB Standard') to return only the passages around them on long pages",
    )


class calculator(BaseModel):
    """Evaluate an arithmetic expression exactly, e.g. '10 * 0.33 + 50'. Use for any cost or number crunching."""

    expression: str = Field(description="Arithmetic expression using + - * / ** ( ) and sqrt, log, round, min, max")


TOOL_SCHEMAS = [web_search, fetch_page, calculator]


def canonical_url(url: str) -> str:
    """Key for deduplication: 'https://www.X.io/pricing/?utm_source=y#top' == 'http://x.io/pricing'."""
    parts = urlsplit(url.strip())
    host = parts.netloc.lower().removeprefix("www.")
    query = urlencode([(k, v) for k, v in parse_qsl(parts.query) if not k.lower().startswith("utm")])
    return f"{host}{parts.path.rstrip('/')}" + (f"?{query}" if query else "")


def register_sources(existing: list[dict], results: list[dict]) -> tuple[list[dict], list[dict]]:
    """Add results to the global source list (dedup by canonical URL); return (all_sources, sources_for_these_results)."""
    sources = list(existing)
    by_key = {canonical_url(s["url"]): s for s in sources}
    matched = []
    for r in results:
        key = canonical_url(r["url"])
        src = by_key.get(key)
        if src is None:
            src = {**r, "id": len(sources) + 1}
            sources.append(src)
        else:
            updated = dict(src)
            if r.get("content") and r["content"] not in src.get("content", ""):
                # Keep every text the agent has seen for this URL (snippet + fetched page) so the
                # citation check can verify any number it was shown.
                updated["content"] = (src.get("content", "") + "\n\n" + r["content"]).strip()
            if r.get("provider") == "fetch":
                updated["provider"] = "fetch"  # the full page has now been read
            if updated != src:
                src = updated
                sources[src["id"] - 1] = src
        by_key[key] = src
        matched.append(src)
    return sources, matched


def run_tool(name: str, args: dict, sources: list[dict]) -> tuple[str, list[dict]]:
    """Execute a tool call. Returns (observation text for the LLM, updated sources). Never raises."""
    try:
        if name == "web_search":
            results = _web_search(args["query"])
            if not results:
                return "No results found. Try a different query.", sources
            sources, matched = register_sources(sources, results)
            provider = results[0].get("provider", "")
            body = "\n\n".join(f"[{s['id']}] {s['title']}\nURL: {s['url']}\n{r['content']}" for s, r in zip(matched, results))
            return f"({provider}) {len(matched)} results:\n\n{body}", sources
        if name == "fetch_page":
            page = _fetch_page(args["url"])
            sources, (src,) = register_sources(sources, [{**page, "provider": "fetch"}])
            view = page_view(page["content"], args.get("focus"))
            return f"[{src['id']}] {src['title']}\nURL: {src['url']}\n\n{view}", sources
        if name == "calculator":
            return f"{args['expression']} = {calculate(args['expression'])}", sources
        return f"Error: unknown tool {name!r}. Available: web_search, fetch_page, calculator.", sources
    except Exception as exc:  # tool errors become observations so the agent can recover
        return f"Error from {name}: {type(exc).__name__}: {str(exc)[:300]}", sources
