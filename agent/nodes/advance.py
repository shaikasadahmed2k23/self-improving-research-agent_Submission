"""Advance node: record the finished step's findings, reset the scratchpad, move to the next step."""
from langchain_core.messages import RemoveMessage
from langgraph.graph.message import REMOVE_ALL_MESSAGES

from agent.llm import text_of
from agent.nodes.writer import normalize_citations
from agent.state import AgentState, event


def advance(state: AgentState) -> dict:
    idx = state["current_step"]
    plan = [dict(s) for s in state["plan"]]
    step = plan[idx]
    result = normalize_citations(text_of(state["messages"][-1]))
    step["result"] = result or "No findings could be extracted for this step."
    step["status"] = "done"
    plan[idx] = step
    return {
        "plan": plan,
        "current_step": idx + 1,
        "step_iterations": 0,
        "messages": [RemoveMessage(id=REMOVE_ALL_MESSAGES)],
        "trace": [event("advance", "result", f"Step {step['id']} findings:\n{step['result']}")],
    }


def route_after_advance(state: AgentState) -> str:
    return "executor" if state["current_step"] < len(state["plan"]) else "writer"
