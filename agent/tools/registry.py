"""LLM-facing tool schemas and the dispatcher the tools node uses.

Schemas are pydantic models (class name = tool name, docstring = description), so the
LLM sees clean signatures while execution stays in our own node. That lets tool results
be registered as numbered citation sources in the shared state.
"""
from pydantic import BaseModel, Field

from agent.tools.calculator import calculate
from agent.tools.fetch import fetch_page as _fetch_page
from agent.tools.search import web_search as _web_search


class web_search(BaseModel):
    """Search the web. Returns numbered results (title, URL, snippet). Cite results by their [number]."""

    query: str = Field(description="Focused search query, 3-10 words, using concrete names (no placeholders)")


class fetch_page(BaseModel):
    """Read the main text of a web page (e.g. an official pricing page) when snippets are not detailed enough."""

    url: str = Field(description="Full http(s) URL, usually one returned by web_search")


class calculator(BaseModel):
    """Evaluate an arithmetic expression exactly, e.g. '10 * 0.33 + 50'. Use for any cost or number crunching."""

    expression: str = Field(description="Arithmetic expression using + - * / ** ( ) and sqrt, log, round, min, max")


TOOL_SCHEMAS = [web_search, fetch_page, calculator]


def register_sources(existing: list[dict], results: list[dict]) -> tuple[list[dict], list[dict]]:
    """Add results to the global source list (dedup by URL); return (all_sources, sources_for_these_results)."""
    sources = list(existing)
    by_url = {s["url"]: s for s in sources}
    matched = []
    for r in results:
        src = by_url.get(r["url"])
        if src is None:
            src = {**r, "id": len(sources) + 1}
            sources.append(src)
            by_url[src["url"]] = src
        elif len(r.get("content", "")) > len(src.get("content", "")):
            src = {**src, "content": r["content"]}  # keep the richer text (e.g. full page over snippet)
            sources[src["id"] - 1] = src
            by_url[src["url"]] = src
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
            return f"[{src['id']}] {src['title']}\nURL: {src['url']}\n\n{page['content']}", sources
        if name == "calculator":
            return f"{args['expression']} = {calculate(args['expression'])}", sources
        return f"Error: unknown tool {name!r}. Available: web_search, fetch_page, calculator.", sources
    except Exception as exc:  # tool errors become observations so the agent can recover
        return f"Error from {name}: {type(exc).__name__}: {str(exc)[:300]}", sources
