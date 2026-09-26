import pytest

from agent import config
from agent.memory.store import MemoryStore, terms
from agent.nodes import reflect as reflect_mod
from agent.nodes.recall import format_sources, recall
from agent.state import Lesson, Reflection

TASK = "Using Pinecone's official pricing page, what would 10 GB of storage cost per month on the Standard plan?"
SIMILAR = "Using Pinecone's official pricing page, what would 25 GB of storage cost per month on the Standard plan?"
PRICING_URL = "https://www.pinecone.io/pricing/"


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "MEMORY_DB_PATH", tmp_path / "mem.db")
    monkeypatch.setattr(config, "REPORTS_DIR", tmp_path / "reports")
    return MemoryStore()


def _outcome(url=PRICING_URL, verified=2, failed=0, facts=("$0.33", "$50")):
    return {"key": "pinecone.io/pricing", "url": url, "domain": "pinecone.io", "title": "Pricing",
            "fetched": True, "verified": verified, "failed": failed, "facts": list(facts)}


def test_terms_drop_stopwords_and_short_words():
    assert terms("What is the cost of Pinecone's Standard plan?") == {"cost", "pinecone", "standard", "plan"}


def test_recall_finds_lessons_and_trusted_sources_of_similar_runs(store):
    run = store.save_run(TASK, 6, "needs_research", 1)
    store.add_lesson(run, "When a task names an official pricing page, fetch_page it in the first step.", "constraints", ["pricing", "official"])
    store.record_sources(run, [_outcome()])

    memory = store.recall(SIMILAR)
    assert [r["id"] for r in memory["similar_runs"]] == [run]
    assert "fetch_page" in memory["lessons"][0]["text"]
    assert memory["trusted_sources"][0]["url"] == PRICING_URL
    assert memory["trusted_sources"][0]["facts"] == ["$0.33", "$50"]

    unrelated = store.recall("History of the Roman aqueducts")
    assert unrelated == {"similar_runs": [], "lessons": [], "trusted_sources": []}


def test_untrusted_sources_are_not_recalled(store):
    run = store.save_run(TASK, 5, "needs_rewrite", 1)
    store.record_sources(run, [_outcome(verified=0, failed=2, facts=())])
    assert store.recall(SIMILAR)["trusted_sources"] == []


def test_duplicate_lessons_are_merged(store):
    run = store.save_run(TASK, 6, "needs_research", 1)
    first, new1 = store.add_lesson(run, "Fetch the official pricing page when the task asks for it.", "sources", ["pricing"])
    again, new2 = store.add_lesson(run, "Fetch the official pricing page whenever the task asks for it.", "sources", ["pricing"])
    assert new1 and not new2 and first == again
    assert store.lessons()[0]["times_seen"] == 2


def test_lesson_feedback_counts_used_and_helpful(store):
    run1 = store.save_run(TASK, 6, "needs_research", 1)
    lid, _ = store.add_lesson(run1, "Fetch the official pricing page first.", "sources", ["pricing"])
    run2 = store.save_run(SIMILAR, 9, "accept", 0)
    store.mark_lessons_used(run2, [lid], helpful=True)
    lesson = store.lessons()[0]
    assert (lesson["times_used"], lesson["times_helpful"]) == (1, 1)


def test_source_outcomes_count_verified_and_failed_checks():
    sources = [{"id": 1, "url": PRICING_URL, "title": "Pricing", "provider": "fetch"},
               {"id": 2, "url": "https://blog.example.com/p", "title": "Blog", "provider": "tavily"},
               {"id": 3, "url": "https://uncited.io", "title": "", "provider": "tavily"}]
    checks = [{"number": "$0.33", "cited": [1], "status": "verified", "verified_in": [1]},
              {"number": "$50", "cited": [1, 2], "status": "verified", "verified_in": [1]},
              {"number": "$16", "cited": [2], "status": "not_in_source"},
              {"number": "$3.30", "cited": [], "status": "calculated"}]
    out = {o["url"]: o for o in reflect_mod.source_outcomes("Storage $0.33 [1]; minimum $50 [1][2]; reads $16 [2].", sources, checks)}
    assert set(out) == {PRICING_URL, "https://blog.example.com/p"}
    assert (out[PRICING_URL]["verified"], out[PRICING_URL]["facts"], out[PRICING_URL]["fetched"]) == (2, ["$0.33", "$50"], True)
    assert (out["https://blog.example.com/p"]["verified"], out["https://blog.example.com/p"]["failed"]) == (0, 1)


class _FakeLLM:
    def __init__(self, result):
        self.result, self.calls = result, 0

    def invoke(self, messages):
        self.calls += 1
        return self.result


def _final_state(critiques, lessons=()):
    final = critiques[-1]
    return {
        "task": TASK,
        "memory": {"lessons": [{"id": i, "text": "x", "category": "sources"} for i in lessons]},
        "plan": [{"id": 1, "goal": "g", "origin": "initial"}, {"id": 2, "goal": f"fetch_page {PRICING_URL}", "origin": "fixup"}],
        "sources": [{"id": 1, "url": PRICING_URL, "title": "Pricing", "provider": "fetch", "content": "$0.33 per GB"}],
        "checks": [{"number": "$0.33", "cited": [1], "status": "verified", "verified_in": [1]}],
        "draft_raw": "Storage costs $0.33 per GB [1].",
        "draft": "# Report\nStorage costs $0.33 per GB [1].",
        "critique": final,
        "critiques": critiques,
        "revision": len(critiques) - 1,
        "tool_log": [{"step": 2, "tool": "fetch_page", "args": {"url": PRICING_URL}, "error": False}],
    }


def _critique(verdict, score, violations=()):
    return {"verdict": verdict, "score": score, "constraint_violations": list(violations), "issues": [],
            "missing_info": [], "failed_checks": [], "final": verdict == "accept"}


def test_reflect_stores_only_reachable_suggested_sources(store, monkeypatch):
    def fake_fetch(url):
        if "invented" in url:
            raise ValueError("404")
        return {"url": url, "title": "pinecone.io/pricing", "content": "..."}

    monkeypatch.setattr(reflect_mod, "fetch_page", fake_fetch)
    fake = _FakeLLM(Reflection(
        lessons=[Lesson(text="When a task names the official pricing page, fetch_page it first.", category="tools",
                        keywords=["pricing", "official"])],
        source_urls=[PRICING_URL, "https://invented.example.com/pricing"],
    ))
    monkeypatch.setattr(reflect_mod, "get_llm", lambda *a, **k: fake)
    state = _final_state([_critique("needs_research", 3, ["official page never fetched"])] * 2)
    state["checks"], state["draft_raw"] = [], "No citations."  # nothing verified: like a run that never fetched

    out = reflect_mod.reflect(state)
    assert "Suggested source (reachable, not verified yet): " + PRICING_URL in out["trace"][0]["content"]
    [src] = recall({"task": SIMILAR})["memory"]["trusted_sources"]
    assert (src["url"], src["suggested"], src["verified"]) == (PRICING_URL, True, 0)
    assert "not verified yet" in format_sources({"trusted_sources": [src]})


def test_reflect_saves_run_lessons_sources_and_report(store, monkeypatch):
    fake = _FakeLLM(Reflection(lessons=[Lesson(text="When a task names the official pricing page, fetch_page it first.",
                                               category="constraints", keywords=["pricing", "official"])]))
    monkeypatch.setattr(reflect_mod, "get_llm", lambda *a, **k: fake)
    state = _final_state([_critique("needs_research", 5, ["official page never fetched"]), _critique("accept", 9)])

    out = reflect_mod.reflect(state)
    assert fake.calls == 1
    assert store.runs()[0]["revisions"] == 1 and store.runs()[0]["report_path"].endswith(".md")
    assert "fetch_page" in store.lessons()[0]["text"]
    assert store.sources()[0]["url"] == PRICING_URL
    assert "New lesson" in out["trace"][0]["content"]

    # the next similar run recalls both
    memory = recall({"task": SIMILAR})["memory"]
    assert memory["lessons"] and memory["trusted_sources"][0]["url"] == PRICING_URL


def test_reflect_skips_llm_when_first_draft_passed_and_marks_recalled_lessons_helpful(store, monkeypatch):
    run = store.save_run(TASK, 6, "needs_research", 1)
    lid, _ = store.add_lesson(run, "Fetch the official pricing page first.", "sources", ["pricing"])
    fake = _FakeLLM(Reflection())
    monkeypatch.setattr(reflect_mod, "get_llm", lambda *a, **k: fake)

    reflect_mod.reflect(_final_state([_critique("accept", 9)], lessons=[lid]))
    assert fake.calls == 0
    assert store.lessons()[0]["times_helpful"] == 1
