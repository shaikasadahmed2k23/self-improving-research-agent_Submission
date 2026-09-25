from langchain_core.messages import AIMessage, ToolMessage

from agent.nodes import tools_node


def _ai(call_id: str, url: str) -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": "fetch_page", "args": {"url": url}, "id": call_id}])


def test_duplicate_tool_call_is_not_re_executed(monkeypatch):
    calls = []
    monkeypatch.setattr(tools_node, "run_tool", lambda n, a, s: (calls.append(a) or "page text", s))
    first = _ai("1", "https://www.pinecone.io/pricing")
    state = {
        "messages": [first, ToolMessage(content="page text", tool_call_id="1"), _ai("2", "https://www.pinecone.io/pricing/")],
        "sources": [],
    }
    out = tools_node.tools(state)
    assert calls == []  # trailing slash / case differences still count as the same call
    assert out["messages"][0].content.startswith("Duplicate call")
    assert out["messages"][0].tool_call_id == "2"
