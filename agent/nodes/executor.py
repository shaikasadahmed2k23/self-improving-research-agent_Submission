"""Executor node (M1): one web search per step, then the LLM extracts cited findings.

M2 replaces this with a ReAct loop (LLM chooses tools; ToolNode executes them).
"""
from langchain_core.messages import HumanMessage, SystemMessage

from agent.llm import get_llm, text_of
from agent.nodes.writer import normalize_citations
from agent.prompts import EXECUTOR_SYSTEM
from agent.state import AgentState, event
from agent.tools.search import web_search


def _register_sources(existing: list[dict], results: list[dict]) -> tuple[list[dict], list[dict]]:
    """Add new results to the global source list (dedup by URL); return (all_sources, this_step_sources)."""
    sources = list(existing)
    by_url = {s["url"]: s for s in sources}
    step_sources = []
    for r in results:
        src = by_url.get(r["url"])
        if src is None:
            src = {**r, "id": len(sources) + 1}
            sources.append(src)
            by_url[src["url"]] = src
        step_sources.append(src)
    return sources, step_sources


def executor(state: AgentState) -> dict:
    idx = state["current_step"]
    plan = [dict(s) for s in state["plan"]]
    step = plan[idx]
    trace = [event("executor", "action", f"Step {step['id']}: web_search({step['search_query']!r})")]

    results = web_search(step["search_query"])
    sources, step_sources = _register_sources(state.get("sources", []), results)
    if step_sources:
        provider = step_sources[0].get("provider", "?")
        listing = "\n".join(f"[{s['id']}] {s['title']} - {s['url']}" for s in step_sources)
        trace.append(event("executor", "observation", f"{len(step_sources)} results via {provider}:\n{listing}"))
        context = "\n\n".join(f"[{s['id']}] {s['title']} ({s['url']})\n{s['content']}" for s in step_sources)
        llm = get_llm("executor", temperature=0)
        msg = llm.invoke(
            [
                SystemMessage(EXECUTOR_SYSTEM),
                HumanMessage(
                    f"Overall task: {state['task']}\nCurrent step: {step['goal']}\n\nSearch results:\n{context}"
                ),
            ]
        )
        step["result"] = normalize_citations(text_of(msg)) or "No findings extracted."
    else:
        trace.append(event("executor", "error", "Search returned no results."))
        step["result"] = "No search results were found for this step."

    step["status"] = "done"
    plan[idx] = step
    trace.append(event("executor", "result", f"Step {step['id']} findings:\n{step['result']}"))
    return {"plan": plan, "sources": sources, "current_step": idx + 1, "trace": trace}


def route_after_executor(state: AgentState) -> str:
    return "executor" if state["current_step"] < len(state["plan"]) else "writer"
