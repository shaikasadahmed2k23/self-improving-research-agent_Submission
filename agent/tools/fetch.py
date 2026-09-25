"""Fetch a web page and extract its main text.

Tavily Extract is tried first because it renders JavaScript (pricing tables are often client-side
rendered, e.g. pinecone.io/pricing); plain httpx + trafilatura is the keyless fallback.
"""
import logging
import re
from urllib.parse import urlsplit

import httpx
import trafilatura

from agent import config

log = logging.getLogger(__name__)
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; ResearchAgent/1.0; +https://github.com/shaikasadahmed2k23)"}
STORE_CHAR_LIMIT = 20000  # kept in the source record for citation verification
FOCUS_RADIUS = 350


def _tavily_extract(url: str) -> dict | None:
    from tavily import TavilyClient

    res = TavilyClient(api_key=config.TAVILY_API_KEY).extract(urls=[url])
    for r in res.get("results", []):
        text = (r.get("raw_content") or "").strip()
        if text:
            return {"url": r.get("url", url), "title": "", "content": text}
    return None


def _httpx_fetch(url: str) -> dict:
    resp = httpx.get(url, headers=HEADERS, timeout=15, follow_redirects=True)
    resp.raise_for_status()
    ctype = resp.headers.get("content-type", "")
    if "html" not in ctype and "text" not in ctype:
        raise ValueError(f"Unsupported content type {ctype!r} (only HTML/text pages can be read)")
    text = trafilatura.extract(resp.text, include_comments=False, include_tables=True) or ""
    if not text.strip():
        raise ValueError("No readable main text found on the page")
    meta = trafilatura.extract_metadata(resp.text)
    return {"url": str(resp.url), "title": (meta.title if meta and meta.title else ""), "content": text}


def fetch_page(url: str) -> dict:
    """Return {url, title, content} with up to STORE_CHAR_LIMIT chars. Raises ValueError on failure."""
    if not url.startswith(("http://", "https://")):
        raise ValueError(f"Not an http(s) URL: {url}")
    page = None
    if config.TAVILY_API_KEY:
        try:
            page = _tavily_extract(url)
        except Exception as exc:
            log.warning("Tavily extract failed for %s: %s", url, exc)
    if page is None:
        page = _httpx_fetch(url)
    if not page["title"]:  # Tavily Extract returns no title; use a readable "host/path"
        parts = urlsplit(page["url"])
        page["title"] = parts.netloc.removeprefix("www.") + parts.path.rstrip("/")
    page["content"] = page["content"][:STORE_CHAR_LIMIT]
    return page


def page_view(text: str, focus: str | None = None, char_limit: int | None = None) -> str:
    """What the LLM sees: passages around `focus` keywords if given (and found), else the start of the page."""
    limit = char_limit or config.PAGE_CHAR_LIMIT
    if focus:
        terms = [t for t in re.split(r"[,\s]+", focus.lower()) if len(t) > 2]
        spans = []
        for term in terms:
            for m in re.finditer(re.escape(term), text.lower()):
                spans.append((max(0, m.start() - FOCUS_RADIUS), min(len(text), m.end() + FOCUS_RADIUS)))
        if spans:
            spans.sort()
            merged = [list(spans[0])]
            for s, e in spans[1:]:
                if s <= merged[-1][1]:
                    merged[-1][1] = max(merged[-1][1], e)
                else:
                    merged.append([s, e])
            out = " […] ".join(text[s:e] for s, e in merged)
            return out[:limit] + (" …[truncated]" if len(out) > limit else "")
    return text[:limit] + (" …[truncated]" if len(text) > limit else "")
