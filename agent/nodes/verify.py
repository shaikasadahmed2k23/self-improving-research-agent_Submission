"""Verify node: deterministic citation check of the draft (no LLM)."""
from agent.state import AgentState, event
from agent.verification import check_citations, summarize_checks


def verify(state: AgentState) -> dict:
    checks = check_citations(state["draft_raw"], state.get("sources", []), state.get("calculations", []), state["task"])
    return {"checks": checks, "trace": [event("verify", "check", summarize_checks(checks))]}
