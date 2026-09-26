"""Executor node: one ReAct turn for the current plan step.

executor -> (tool calls?) -> tools -> executor -> ... -> (plain answer) -> advance
The LLM sees the whole plan plus the findings of earlier steps, so later steps research the
entities that earlier steps actually identified.
"""
import re
from datetime import date

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from agent import config
from agent.llm import get_llm
from agent.memory.store import terms
from agent.nodes.recall import format_sources
from agent.prompts import EXECUTOR_FINALIZE, EXECUTOR_INVALID_TOOL, EXECUTOR_STEP, EXECUTOR_SYSTEM
from agent.state import AgentState, event
from agent.tools.registry import TOOL_SCHEMAS, canonical_url
from agent.verification import domain

_URL = re.compile(r"https?://[^\s)\]>\"']+")
# Goal words that say *how* to research rather than *what*; left out of the fetch_page focus keywords
_GENERIC_GOAL_TERMS = {
    "fetch", "fetch_page", "page", "official", "pricing", "price", "prices", "extract", "cost", "costs", "monthly",
    "month", "determine", "vendor", "website", "site", "https", "http", "www", "com", "plan", "plans",
}


def _clip(text: str) -> str:
    limit = config.STEP_CONTEXT_CHARS
    return text if not limit or len(text) <= limit else text[:limit] + " …[truncated]"


def _trusted(state: AgentState) -> str:
    memory = state.get("memory") or {}
    if not memory.get("trusted_sources"):
        return ""
    return f"Trusted sources from similar past runs (prefer these):\n{format_sources(memory)}\n"


def _step_prompt(state: AgentState) -> list:
    idx = state["current_step"]
    plan = state["plan"]
    step = plan[idx]
    previous = "\n\n".join(f"Step {s['id']} - {s['goal']}\n{_clip(s['result'])}" for s in plan[:idx])
    human = EXECUTOR_STEP.format(
        task=state["task"],
        plan="\n".join(f"{s['id']}. {s['goal']}" for s in plan),
        previous=previous or "(none yet: this is the first step)",
        step_id=step["id"],
        goal=step["goal"],
        query=step["search_query"],
        trusted=_trusted(state),
    )
    system = EXECUTOR_SYSTEM.format(today=date.today().isoformat(), max_tool_rounds=config.MAX_REACT_ITERATIONS - 1)
    return [SystemMessage(system), HumanMessage(human)]


def executor(state: AgentState) -> dict:
    idx = state["current_step"]
    step = state["plan"][idx]
    iterations = state.get("step_iterations", 0)
    history = list(state.get("messages", []))
    trace = []

    new_messages = []
    if not history:
        new_messages = _step_prompt(state)
        trace.append(event("executor", "thought", f"Starting step {step['id']}/{len(state['plan'])}: {step['goal']}"))
        directed = directed_fetch(state, step)
        if directed:  # read the known page first; no LLM call, so the step keeps its full LLM budget
            args, reason = directed
            ai = AIMessage(content="", tool_calls=[{"name": "fetch_page", "args": args, "id": f"directed_{step['id']}", "type": "tool_call"}])
            shown = ", ".join(f"{k}={v!r}" for k, v in args.items())
            trace.append(event("executor", "action", f"fetch_page({shown})  [directed: {reason}]"))
            return {"messages": new_messages + [ai], "step_iterations": iterations, "trace": trace}

    finalize = iterations >= config.MAX_REACT_ITERATIONS - 1
    if finalize:
        new_messages.append(HumanMessage(EXECUTOR_FINALIZE))
        llm = get_llm("executor", temperature=0)
    else:
        llm = get_llm("executor", tools=TOOL_SCHEMAS, temperature=0)

    try:
        ai = llm.invoke(history + new_messages)
    except Exception as exc:
        if finalize or not _is_invalid_tool_call(exc):
            raise
        # gpt-oss was trained with built-in browser tools (find/open/search) and sometimes calls them;
        # Groq rejects the request. Correct the model once, then fall back to answering without tools.
        trace.append(event("executor", "error", f"Invalid tool call rejected by the API: {_short(exc)}. Retrying with a correction."))
        new_messages.append(HumanMessage(EXECUTOR_INVALID_TOOL))
        try:
            ai = llm.invoke(history + new_messages)
        except Exception as exc2:
            if not _is_invalid_tool_call(exc2):
                raise
            trace.append(event("executor", "error", "Invalid tool call again; answering without tools."))
            new_messages.append(HumanMessage(EXECUTOR_FINALIZE))
            ai = get_llm("executor", temperature=0).invoke(history + new_messages)

    reasoning = (ai.additional_kwargs.get("reasoning_content") or "").strip()
    if reasoning:
        trace.append(event("executor", "thought", reasoning[:500]))
    for call in ai.tool_calls:
        args = ", ".join(f"{k}={v!r}" for k, v in call["args"].items())
        trace.append(event("executor", "action", f"{call['name']}({args})"))

    return {"messages": new_messages + [ai], "step_iterations": iterations + 1, "trace": trace}


def _brand(url: str) -> str:
    """'https://www.pinecone.io/pricing' -> 'pinecone'."""
    parts = domain(url).split(".")
    return parts[-2] if len(parts) >= 2 else parts[0]


def directed_fetch(state: AgentState, step: dict) -> tuple[dict, str] | None:
    """A page the step should read before the LLM decides anything: a URL written in the step goal (fix-up steps and
    memory-informed plans put it there), else a trusted page from memory about a site the goal names. Small models
    often ignore such instructions and search again, so this is done in code. Pages already fetched are skipped."""
    fetched = {canonical_url(s["url"]) for s in state.get("sources", []) if s.get("provider") == "fetch"}
    goal_terms = terms(step["goal"])
    trusted = (state.get("memory") or {}).get("trusted_sources", [])
    facts_of = {canonical_url(s["url"]): s["facts"] for s in trusted}
    candidates = [
        (u.rstrip(".,"), "URL named in the step goal", facts_of.get(canonical_url(u.rstrip(".,")), []))
        for u in _URL.findall(step["goal"])
    ]
    candidates += [
        (s["url"], "trusted source from memory", s["facts"])
        for s in trusted
        if (s["fetched"] or s["suggested"]) and _brand(s["url"]) in goal_terms
    ]
    for url, reason, facts in candidates:
        if canonical_url(url) in fetched:
            continue
        # Focus on what the task is about (goals can be vague, e.g. "fetch the page to ensure accurate data"),
        # plus figures this page verified before: they mark the passages that mattered last time.
        topic = (goal_terms | terms(state.get("task", ""))) - _GENERIC_GOAL_TERMS - {_brand(url)}
        focus = " ".join(sorted(topic) + list(facts[:3]))
        return ({"url": url, "focus": focus} if focus else {"url": url}), reason
    return None


def _is_invalid_tool_call(exc: Exception) -> bool:
    msg = str(exc)
    return "tool_use_failed" in msg or "Failed to parse tool call" in msg or "not in request.tools" in msg


def _short(exc: Exception) -> str:
    msg = str(exc)
    start = msg.find("attempted to call tool")
    return msg[start : start + 80] if start >= 0 else msg[:120]


def route_after_executor(state: AgentState) -> str:
    last = state["messages"][-1]
    return "tools" if getattr(last, "tool_calls", None) else "advance"
