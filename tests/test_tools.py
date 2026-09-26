import pytest

from agent.tools import registry
from agent.tools.calculator import calculate


@pytest.mark.parametrize(
    "expr, expected",
    [("10 * 0.33 + 50", 53.3), ("2^10", 1024), ("1,000,000 / 4", 250000), ("round(sqrt(2) * 3, 2)", 4.24), ("-(3 - 5)", 2)],
)
def test_calculator(expr, expected):
    assert calculate(expr) == expected


@pytest.mark.parametrize("expr", ["__import__('os')", "open('x')", "10 ** 10 ** 10", "a + 1"])
def test_calculator_rejects_unsafe(expr):
    with pytest.raises(Exception):
        calculate(expr)


def test_register_sources_dedups_and_keeps_all_seen_text():
    sources, matched = registry.register_sources([], [{"url": "u1", "title": "A", "content": "snippet $0.33"}])
    sources, matched = registry.register_sources(
        sources, [{"url": "u1", "title": "A", "content": "full page text"}, {"url": "u2", "title": "B", "content": ""}]
    )
    assert [s["id"] for s in sources] == [1, 2]
    assert "snippet $0.33" in sources[0]["content"] and "full page text" in sources[0]["content"]
    assert [m["id"] for m in matched] == [1, 2]


def test_run_tool_numbers_search_results(monkeypatch):
    fake = [{"title": "T", "url": "https://a.io", "content": "snippet", "provider": "tavily"}]
    monkeypatch.setattr(registry, "_web_search", lambda q: fake)
    existing = [{"id": 1, "title": "Old", "url": "https://old.io", "content": ""}]
    text, sources = registry.run_tool("web_search", {"query": "q"}, existing)
    assert "[2] T" in text and len(sources) == 2


def test_run_tool_errors_become_observations():
    text, sources = registry.run_tool("fetch_page", {"url": "ftp://nope"}, [])
    assert text.startswith("Error from fetch_page") and sources == []
    text, _ = registry.run_tool("calculator", {"expression": "1/0"}, [])
    assert "ZeroDivisionError" in text
    text, _ = registry.run_tool("bogus", {}, [])
    assert "unknown tool" in text


def test_canonical_url_merges_trailing_slash_www_and_utm():
    a = registry.canonical_url("https://www.pinecone.io/pricing/")
    assert a == registry.canonical_url("https://pinecone.io/pricing?utm_source=x")
    assert a != registry.canonical_url("https://www.pinecone.io/pricing/estimate")


def test_search_snippet_and_fetched_page_become_one_source():
    sources, _ = registry.register_sources(
        [], [{"url": "https://www.pinecone.io/pricing", "title": "Pricing", "content": "Storage $0.33/GB/mo", "provider": "tavily"}]
    )
    sources, (src,) = registry.register_sources(
        sources, [{"url": "https://www.pinecone.io/pricing/", "title": "Pricing | Pinecone", "content": "$50/month min", "provider": "fetch"}]
    )
    assert len(sources) == 1 and src["id"] == 1
    assert "$0.33" in src["content"] and "$50" in src["content"] and src["provider"] == "fetch"


def test_page_view_focuses_on_keywords():
    from agent.tools.fetch import page_view

    text = "intro " * 2000 + "| Storage | Unlimited $0.33/GB/mo |" + " outro" * 2000
    view = page_view(text, focus="storage", char_limit=3000)
    assert "$0.33/GB/mo" in view and len(view) < 3100
    assert page_view(text, char_limit=100).startswith("intro")


def test_page_view_covers_every_focus_term_within_the_limit():
    from agent.tools.fetch import page_view

    minimum = "Standard plan minimum commitment rate: $50/month minimum usage. " * 8  # matches many word terms
    price = "| Storage | Unlimited $0.33/GB/mo |"  # matches the specific figure only
    text = "intro " * 200 + minimum + "filler " * 300 + price + " tail" * 50
    view = page_view(text, focus="standard minimum commitment rate storage $0.33", char_limit=1000)
    assert "$50/month" in view and "$0.33/GB/mo" in view
    assert len(view) <= 1000 + len(" […] ") + len(" …[truncated]")
