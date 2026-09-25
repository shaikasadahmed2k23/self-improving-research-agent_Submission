"""Executor node: one ReAct turn for the current plan step.

executor -> (tool calls?) -> tools -> executor -> ... -> (plain answer) -> advance
The LLM sees the whole plan plus the findings of earlier steps, so later steps research the
entities that earlier steps actually identified.
"""
from datetime import date

from langchain_core.messages import HumanMessage, SystemMessage

from agent import config
from agent.llm import get_llm
from agent.prompts import EXECUTOR_FINALIZE, EXECUTOR_STEP, EXECUTOR_SYSTEM
from agent.state import AgentState, event
from agent.tools.registry import TOOL_SCHEMAS


def _step_prompt(state: AgentState) -> list:
    idx = state["current_step"]
    plan = state["plan"]
    step = plan[idx]
    previous = "\n\n".join(f"Step {s['id']} - {s['goal']}\n{s['result']}" for s in plan[:idx])
    human = EXECUTOR_STEP.format(
        task=state["task"],
        plan="\n".join(f"{s['id']}. {s['goal']}" for s in plan),
        previous=previous or "(none yet: this is the first step)",
        step_id=step["id"],
        goal=step["goal"],
        query=step["search_query"],
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

    finalize = iterations >= config.MAX_REACT_ITERATIONS - 1
    if finalize:
        new_messages.append(HumanMessage(EXECUTOR_FINALIZE))
        llm = get_llm("executor", temperature=0)
    else:
        llm = get_llm("executor", tools=TOOL_SCHEMAS, temperature=0)

    ai = llm.invoke(history + new_messages)

    reasoning = (ai.additional_kwargs.get("reasoning_content") or "").strip()
    if reasoning:
        trace.append(event("executor", "thought", reasoning[:500]))
    for call in ai.tool_calls:
        args = ", ".join(f"{k}={v!r}" for k, v in call["args"].items())
        trace.append(event("executor", "action", f"{call['name']}({args})"))

    return {"messages": new_messages + [ai], "step_iterations": iterations + 1, "trace": trace}


def route_after_executor(state: AgentState) -> str:
    last = state["messages"][-1]
    return "tools" if getattr(last, "tool_calls", None) else "advance"
