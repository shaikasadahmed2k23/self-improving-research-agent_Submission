"""Fetch a web page and extract its main text."""
import httpx
import trafilatura

from agent import config

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; ResearchAgent/1.0; +https://github.com/shaikasadahmed2k23)"}


def fetch_page(url: str, char_limit: int | None = None) -> dict:
    """Return {url, title, content}. Raises ValueError with a readable message on failure."""
    if not url.startswith(("http://", "https://")):
        raise ValueError(f"Not an http(s) URL: {url}")
    resp = httpx.get(url, headers=HEADERS, timeout=15, follow_redirects=True)
    resp.raise_for_status()
    ctype = resp.headers.get("content-type", "")
    if "html" not in ctype and "text" not in ctype:
        raise ValueError(f"Unsupported content type {ctype!r} (only HTML/text pages can be read)")

    text = trafilatura.extract(resp.text, include_comments=False, include_tables=True) or ""
    meta = trafilatura.extract_metadata(resp.text)
    title = (meta.title if meta and meta.title else "") or url
    if not text.strip():
        raise ValueError("No readable main text found on the page")
    limit = char_limit or config.PAGE_CHAR_LIMIT
    if len(text) > limit:
        text = text[:limit] + " …[truncated]"
    return {"url": str(resp.url), "title": title, "content": text}
