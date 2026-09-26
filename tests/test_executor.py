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


def _step_state(goal, memory=None, sources=()):
    plan = [{"id": 1, "goal": goal, "search_query": "q", "status": "pending", "result": ""}]
    return {**STATE, "plan": plan, "memory": memory or {}, "sources": list(sources)}


TRUSTED = {"trusted_sources": [{"url": "https://www.pinecone.io/pricing", "title": "", "verified": 2, "fetched": True,
                                "suggested": False, "facts": ["$0.33"]}]}


def test_step_with_url_in_goal_fetches_it_without_an_llm_call(monkeypatch):
    monkeypatch.setattr(executor_mod, "get_llm", lambda *a, **k: FakeLLM([]))  # any LLM call would fail
    out = executor_mod.executor(_step_state("fetch_page https://www.pinecone.io/pricing/ and extract the storage cost"))
    [call] = out["messages"][-1].tool_calls
    assert call["name"] == "fetch_page" and call["args"]["url"] == "https://www.pinecone.io/pricing/"
    assert out["step_iterations"] == 0
    assert executor_mod.route_after_executor({"messages": out["messages"]}) == "tools"


def test_trusted_page_from_memory_is_read_for_a_step_about_that_site():
    goal = {"goal": "Find Pinecone's Standard plan storage cost for 25 GB"}
    args, reason = executor_mod.directed_fetch(_step_state(goal["goal"], TRUSTED), goal)
    assert args == {"url": "https://www.pinecone.io/pricing", "focus": "standard storage $0.33"}
    assert "memory" in reason


def test_no_directed_fetch_when_already_fetched_or_site_not_named():
    fetched = [{"id": 1, "url": "https://pinecone.io/pricing/", "provider": "fetch"}]
    goal = {"goal": "Find Pinecone's Standard plan storage cost"}
    assert executor_mod.directed_fetch(_step_state(goal["goal"], TRUSTED, fetched), goal) is None
    goal = {"goal": "Find Qdrant Cloud's free tier limits"}
    assert executor_mod.directed_fetch(_step_state(goal["goal"], TRUSTED), goal) is None
