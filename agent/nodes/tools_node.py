"""Tools node: execute the executor's tool calls and register results as citation sources."""
import re

from langchain_core.messages import ToolMessage

from agent.state import AgentState, event
from agent.tools.registry import run_tool

_RESULT_HEADER = re.compile(r"^\[\d+\] .+$", re.MULTILINE)


def _trace_summary(name: str, text: str) -> str:
    """Short, readable version of an observation for the live trace."""
    if name == "web_search" and not text.startswith("Error"):
        headers = _RESULT_HEADER.findall(text)
        return text.splitlines()[0] + "\n" + "\n".join(headers)
    return text if len(text) <= 400 else text[:400] + " …"


def _call_key(call: dict) -> tuple:
    return call["name"], tuple(sorted((k, str(v).strip().lower().rstrip("/")) for k, v in call["args"].items()))


def tools(state: AgentState) -> dict:
    ai = state["messages"][-1]
    sources = state.get("sources", [])
    # Tool calls already made in this step (the scratchpad is reset per step).
    seen = {_call_key(c) for m in state["messages"][:-1] for c in getattr(m, "tool_calls", None) or []}
    messages, trace = [], []
    for call in ai.tool_calls:
        key = _call_key(call)
        if key in seen:
            text = (
                f"Duplicate call: {call['name']} was already called with these arguments in this step. "
                "Its result is above. Use it, try something different, or give your final answer."
            )
        else:
            text, sources = run_tool(call["name"], call["args"], sources)
        seen.add(key)
        messages.append(ToolMessage(content=text, tool_call_id=call["id"], name=call["name"]))
        kind = "error" if text.startswith("Error") else "observation"
        trace.append(event("tools", kind, _trace_summary(call["name"], text)))
    return {"messages": messages, "sources": sources, "trace": trace}
