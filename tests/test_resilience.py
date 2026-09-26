"""M6: rate-limit retries, graceful stop with a partial report, tool errors as observations."""
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda
from streamlit.testing.v1 import AppTest

from agent import config, llm, runner
from agent.nodes import tools_node
from agent.tools import registry


class RateLimited(Exception):
    status_code = 429


DAILY = RateLimited("Rate limit reached for model `openai/gpt-oss-20b` on tokens per day (TPD): Limit 200000, Used 199283, "
                    "Requested 4828. Please try again in 29m35.952s.")
PER_MINUTE = RateLimited("Rate limit reached ... on output tokens per minute (OTPM). Please try again in 1.5s.")


@pytest.mark.parametrize("text, seconds", [
    ("Please try again in 29m35.952s.", 29 * 60 + 35.952),
    ("Please try again in 20.759999999s.", 20.759999999),
    ("Please try again in 1h2m3s", 3723),
    ("429 RESOURCE_EXHAUSTED {'retryDelay': '34s'}", 34),
    ("no hint here", None),
])
def test_retry_after_parses_provider_messages(text, seconds):
    got = llm.retry_after(RateLimited(text))
    assert got == pytest.approx(seconds) if seconds is not None else got is None


def _flaky(errors, result="ok"):
    calls = []

    def run(value):
        calls.append(value)
        if errors:
            raise errors.pop(0)
        return result

    return RunnableLambda(run), calls


def test_short_rate_limits_are_waited_out_on_the_same_model(monkeypatch):
    waits = []
    monkeypatch.setattr(llm.time, "sleep", waits.append)
    inner, calls = _flaky([PER_MINUTE, RateLimited("429 Too Many Requests")])
    assert llm.with_rate_limit_retry(inner).invoke("x") == "ok"
    assert len(calls) == 3
    assert 1.5 <= waits[0] < 2.1  # provider's retry-after (+ jitter)
    assert 4.0 <= waits[1] < 4.6  # no hint: exponential backoff (2s * 2**attempt)


def test_daily_quota_and_other_errors_are_raised_at_once(monkeypatch):
    monkeypatch.setattr(llm.time, "sleep", lambda s: pytest.fail("must not wait"))
    for err in (DAILY, ValueError("bad request")):
        inner, calls = _flaky([err])
        with pytest.raises(type(err)):
            llm.with_rate_limit_retry(inner).invoke("x")
        assert len(calls) == 1


def test_fallback_chain_moves_on_after_daily_quota(monkeypatch):
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)
    first, _ = _flaky([DAILY])
    second, calls = _flaky([], result="from fallback")
    chain = llm.with_rate_limit_retry(first).with_fallbacks([llm.with_rate_limit_retry(second)])
    assert chain.invoke("x") == "from fallback" and len(calls) == 1


class _StoppingGraph:
    """Streams a finished step, then fails like an exhausted fallback chain."""

    def stream(self, *a, **k):
        yield {"planner": {"plan": [{"id": 1, "goal": "Find the price", "status": "pending", "result": "", "origin": "initial"},
                                    {"id": 2, "goal": "Compare plans", "status": "pending", "result": "", "origin": "initial"}],
                           "current_step": 0, "trace": [{"node": "planner", "kind": "plan", "content": "1. Find the price"}]}}
        yield {"tools": {"sources": [{"id": 1, "title": "Pricing", "url": "https://www.pinecone.io/pricing/", "content": "x" * 5000}]}}
        yield {"advance": {"plan": [{"id": 1, "goal": "Find the price", "status": "done", "result": "- Storage is $0.33/GB/mo [1]",
                                     "origin": "initial"},
                                    {"id": 2, "goal": "Compare plans", "status": "pending", "result": "", "origin": "initial"}],
                           "current_step": 1}}
        raise DAILY


def test_run_that_runs_out_of_quota_stops_with_a_partial_report(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "REPORTS_DIR", tmp_path / "reports")
    monkeypatch.setattr(config, "TRACES_DIR", tmp_path / "traces")
    monkeypatch.setattr("agent.graph.build_graph", lambda use_memory=True: _StoppingGraph())

    updates = list(runner.stream_run("What does Pinecone storage cost?"))  # must not raise
    nodes = [n for n, _ in updates]
    assert nodes[-2:] == ["stopped", "done"]
    assert all("content" not in s for _, d in updates for s in d.get("sources", []))  # page text is not streamed

    stopped = dict(updates)["stopped"]
    assert stopped["stopped"]["kind"] == "quota"
    report = stopped["draft"]
    assert "Partial report" in report and "$0.33/GB/mo [1]" in report
    assert "## Not researched yet\n- Compare plans" in report
    assert "## Sources\n1. [Pricing](https://www.pinecone.io/pricing/)" in report
    assert Path(config.ROOT_DIR / stopped["report_path"]).exists() or Path(stopped["report_path"]).exists()
    assert list((tmp_path / "traces").glob("*.jsonl"))  # the trace is kept too


def test_tool_crash_becomes_an_observation(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("provider exploded")

    monkeypatch.setattr(tools_node, "run_tool", boom)
    state = {"messages": [AIMessage(content="", tool_calls=[{"name": "web_search", "args": {"query": "q"}, "id": "1"}])],
             "plan": [{"id": 1}], "current_step": 0, "sources": []}
    out = tools_node.tools(state)
    assert out["messages"][0].content.startswith("Error from web_search: RuntimeError: provider exploded")
    assert out["tool_log"][0]["error"] is True and out["trace"][0]["kind"] == "error"


@pytest.mark.parametrize("name, args", [("web_search", {}), ("calculator", {"expression": "1/0"}), ("nope", {})])
def test_bad_tool_calls_return_error_observations(name, args):
    text, sources = registry.run_tool(name, args, [])
    assert text.startswith("Error") and sources == []


def test_ui_suggests_replay_when_a_live_run_hits_quota(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "MEMORY_DB_PATH", tmp_path / "m.db")
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    stopped = {"kind": "quota", "message": "Every language model in the fallback chain is out of free-tier quota.",
               "detail": "RateLimitError: 429"}
    monkeypatch.setattr("agent.runner.stream_run", lambda task, use_memory=True, record_trace=True: iter([
        ("start", {"task": task}),
        ("stopped", {"stopped": stopped, "draft": "> **Partial report.**\n# Partial findings", "report_path": "r.md",
                     "trace": [{"node": "runner", "kind": "error", "content": "stopped"}]}),
        ("done", {"tokens": {}}),
    ]))
    at = AppTest.from_file(str(Path(config.ROOT_DIR) / "app.py"), default_timeout=30).run()
    at.text_area[0].set_value("anything").run()
    at.button[0].click().run()
    assert not at.exception
    assert any("Run stopped" in e.value for e in at.error)
    assert any("Replay a recorded run" in i.value for i in at.info)
    assert any("Partial findings" in m.value for m in at.markdown)
