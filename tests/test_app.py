"""UI tests: drive app.py with Streamlit's AppTest on a recorded trace (no LLM calls)."""
import json
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from agent import config
from agent.memory.store import MemoryStore
from agent.replay import from_cli_log, load_trace
from agent.runner import fold, record

APP = str(Path(__file__).resolve().parent.parent / "app.py")
PLAN = [{"id": 1, "goal": "Fetch the official pricing page", "search_query": "q", "status": "pending", "result": "", "origin": "initial"}]
UPDATES = [
    ("start", {"task": "What does 25 GB cost on Pinecone Standard?", "use_memory": True}),
    ("recall", {"memory": {}, "trace": [{"node": "recall", "kind": "memory", "content": "Lessons:\n- fetch the official page"}]}),
    ("planner", {"plan": PLAN, "current_step": 0, "trace": [{"node": "planner", "kind": "plan", "content": "1. Fetch the official pricing page"}]}),
    ("executor", {"trace": [{"node": "executor", "kind": "action", "content": "fetch_page(url='https://www.pinecone.io/pricing/')"}]}),
    ("tools", {"trace": [{"node": "tools", "kind": "observation", "content": "[1] Pricing\n$0.33/GB/mo"}]}),
    ("advance", {"plan": [{**PLAN[0], "status": "done"}], "current_step": 1,
                 "trace": [{"node": "advance", "kind": "result", "content": "Step 1 findings:\n- $0.33/GB/mo [1]"}]}),
    ("writer", {"draft": "# Pinecone storage cost\n25 GB costs $8.25 per month [1].\n", "trace": [{"node": "writer", "kind": "report", "content": "Draft written"}]}),
    ("verify", {"trace": [{"node": "verify", "kind": "check", "content": "Citation check: 1 verified"}]}),
    ("critic", {"critique": {"score": 9, "verdict": "accept"}, "revision": 0,
                "trace": [{"node": "critic", "kind": "critique", "content": "Score 9/10 -> accept"}]}),
    ("reflect", {"run_id": 1, "trace": [{"node": "reflect", "kind": "lesson", "content": "Run #1 saved"}]}),
    ("done", {"tokens": {"qwen/qwen3.8-27b": {"input_tokens": 900, "output_tokens": 100, "total_tokens": 1000}}}),
]


@pytest.fixture
def env(tmp_path, monkeypatch):
    for name, value in {"DATA_DIR": tmp_path, "TRACES_DIR": tmp_path / "traces", "SAMPLE_TRACES_DIR": tmp_path / "samples",
                        "MEMORY_DB_PATH": tmp_path / "agent_memory.db"}.items():
        monkeypatch.setattr(config, name, value)
    list(record(tmp_path / "traces" / "20260926-120000-pinecone.jsonl", UPDATES))
    store = MemoryStore()
    run = store.save_run("What does 10 GB cost on Pinecone Standard?", 9, "accept", 1)
    store.set_run_tokens(run, 17041)
    store.add_lesson(run, "When a task names an official pricing page, fetch_page it first.", "sources", ["pricing"])
    store.record_sources(run, [{"key": "pinecone.io/pricing", "url": "https://www.pinecone.io/pricing/", "domain": "pinecone.io",
                                "title": "Pricing", "fetched": True, "verified": 2, "failed": 0, "facts": ["$0.33"]}])
    return tmp_path


def test_recorded_trace_round_trips(env):
    assert load_trace(env / "traces" / "20260926-120000-pinecone.jsonl") == [(n, json.loads(json.dumps(d))) for n, d in UPDATES]


def test_replay_shows_plan_trace_metrics_and_report(env):
    at = AppTest.from_file(APP, default_timeout=30).run()
    assert not at.exception
    at.sidebar.radio[0].set_value("Replay a recorded run").run()
    at.slider[0].set_value(0.0)
    at.button[0].click().run()
    assert not at.exception

    text = " ".join(m.value for m in at.markdown)
    assert "✅ **1.** Fetch the official pricing page" in text  # plan checklist, step done
    assert "# Pinecone storage cost" in text  # final report
    labels = [e.label for e in at.expander]
    for label in ("MEMORY", "PLAN", "ACT", "OBSERVE", "VERIFY", "CRITIQUE", "LEARN"):
        assert any(f"**{label}**" in l for l in labels), label
    assert {m.label: m.value for m in at.metric}["Critic score"] == "9/10"
    assert any("Tokens: 1,000" in c.value for c in at.caption)


def test_memory_tab_lists_lessons_sources_and_runs(env):
    at = AppTest.from_file(APP, default_timeout=30).run()
    assert not at.exception
    metrics = {m.label: m.value for m in at.metric}
    assert (metrics["Runs"], metrics["Lessons"], metrics["Trusted sources"]) == ("1", "1", "1")
    frames = [d.value for d in at.dataframe]
    assert any("fetch_page it first" in " ".join(map(str, f["text"])) for f in frames if "text" in f)
    assert any("https://www.pinecone.io/pricing/" in list(f["url"]) for f in frames if "url" in f)


def test_memory_toggle_is_passed_to_live_runs(env, monkeypatch):
    calls = []

    def fake_stream_run(task, use_memory=True, record_trace=True):
        calls.append(use_memory)
        return iter(UPDATES)

    monkeypatch.setattr("agent.runner.stream_run", fake_stream_run)
    at = AppTest.from_file(APP, default_timeout=30).run()
    at.sidebar.toggle[0].set_value(False)
    at.text_area[0].set_value("What does 25 GB cost on Pinecone Standard?").run()
    at.button[0].click().run()
    assert not at.exception
    assert calls == [False]


CLI_LOG = """TASK: What does 10 GB cost?

[planner] PLAN
    1. Find the price  (search: pinecone price)

[advance] RESULT
    Step 1 findings:
    - $0.33/GB [1]

[critic] CRITIQUE
    Score 9/10 -> accept
    Accepted.

================================================================================
# Report
Text [1]

Critic: 9/10, verdict=accept, revisions=0
Tools used: web_search x1
Tokens [openai/gpt-oss-20b]: 1,234 (in 1,000 / out 234)
"""


def test_cli_log_replay_rebuilds_plan_report_and_tokens():
    updates = from_cli_log(CLI_LOG)
    state: dict = {}
    for node, delta in updates[1:-1]:
        fold(state, delta)
    assert updates[0] == ("start", {"task": "What does 10 GB cost?", "use_memory": False})
    assert state["plan"][0]["status"] == "done" and state["plan"][0]["goal"] == "Find the price"
    assert state["critique"] == {"score": 9, "verdict": "accept"} and state["revision"] == 0
    assert state["draft"].startswith("# Report")
    assert updates[-1][1]["tokens"]["openai/gpt-oss-20b"]["total_tokens"] == 1234
