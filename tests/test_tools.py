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


def test_register_sources_dedups_and_keeps_richer_content():
    sources, matched = registry.register_sources([], [{"url": "u1", "title": "A", "content": "short"}])
    sources, matched = registry.register_sources(
        sources, [{"url": "u1", "title": "A", "content": "much longer text"}, {"url": "u2", "title": "B", "content": ""}]
    )
    assert [s["id"] for s in sources] == [1, 2]
    assert sources[0]["content"] == "much longer text"
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
