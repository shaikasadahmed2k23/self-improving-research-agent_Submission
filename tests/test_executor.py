from langchain_core.messages import AIMessage

from agent.nodes import executor as executor_mod

STATE = {
    "task": "t",
    "plan": [{"id": 1, "goal": "g", "search_query": "q", "status": "pending", "result": ""}],
    "current_step": 0,
    "messages": [],
    "step_iterations": 0,
}
INVALID = Exception("Error code: 400 - tool_use_failed: attempted to call tool 'find' which was not in request.tools")


class FakeLLM:
    def __init__(self, responses):
        self.responses, self.seen = list(responses), []

    def invoke(self, messages):
        self.seen.append(messages)
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def test_invalid_tool_call_is_corrected_and_retried(monkeypatch):
    good = AIMessage(content="", tool_calls=[{"name": "web_search", "args": {"query": "x"}, "id": "1"}])
    fake = FakeLLM([INVALID, good])
    monkeypatch.setattr(executor_mod, "get_llm", lambda *a, **k: fake)
    out = executor_mod.executor(STATE)
    assert out["messages"][-1] is good
    assert "no find/open/search/browser tool" in fake.seen[1][-1].content
    assert any(e["kind"] == "error" for e in out["trace"])


def test_second_invalid_call_falls_back_to_answer_without_tools(monkeypatch):
    answer = AIMessage(content="- fact [1]")
    fake = FakeLLM([INVALID, INVALID, answer])
    monkeypatch.setattr(executor_mod, "get_llm", lambda *a, **k: fake)
    out = executor_mod.executor(STATE)
    assert out["messages"][-1] is answer
    assert executor_mod.route_after_executor({"messages": out["messages"]}) == "advance"


def test_other_errors_still_raise(monkeypatch):
    fake = FakeLLM([RuntimeError("quota exhausted")])
    monkeypatch.setattr(executor_mod, "get_llm", lambda *a, **k: fake)
    try:
        executor_mod.executor(STATE)
    except RuntimeError:
        return
    raise AssertionError("expected RuntimeError")
