"""Planner node: turn the task into research steps; after a critic rejection, append fix-up steps only."""
from datetime import date

from langchain_core.messages import HumanMessage, SystemMessage

from agent import config
from agent.llm import get_llm
from agent.nodes.recall import format_lessons, format_sources, has_memory
from agent.prompts import PLANNER_FIXUP_SYSTEM, PLANNER_MEMORY, PLANNER_SYSTEM
from agent.state import AgentState, Plan, PlanStep, event

MAX_FIXUP_STEPS = 3


def _as_dicts(steps: list[PlanStep], start_id: int, origin: str) -> list[dict]:
    return [
        {"id": start_id + i, "goal": s.goal, "search_query": s.search_query, "status": "pending", "result": "", "origin": origin}
        for i, s in enumerate(steps)
    ]


def _summary(steps: list[dict]) -> str:
    return "\n".join(f"{s['id']}. {s['goal']}  (search: {s['search_query']})" for s in steps)


def _memory_block(state: AgentState) -> str:
    memory = state.get("memory")
    return PLANNER_MEMORY.format(lessons=format_lessons(memory), sources=format_sources(memory)) if has_memory(memory) else ""


def planner(state: AgentState) -> dict:
    critique = state.get("critique")
    if critique and critique.get("verdict") == "needs_research" and not critique.get("final"):
        return replan(state)

    task = state["task"]
    llm = get_llm("planner", schema=Plan, temperature=0)
    system = PLANNER_SYSTEM.format(today=date.today().isoformat(), min_steps=1, max_steps=config.MAX_PLAN_STEPS)
    memory_block = _memory_block(state)
    plan: Plan = llm.invoke([SystemMessage(system), HumanMessage(f"Research task: {task}{memory_block}")])

    steps = plan.steps[: config.MAX_PLAN_STEPS] if plan and plan.steps else []
    if not steps:  # degenerate output: fall back to a single direct search
        steps = [PlanStep(goal=task, search_query=task)]
    plan_dicts = _as_dicts(steps, 1, "initial")
    trace = [event("planner", "memory", "Planner prompt includes memory:" + memory_block)] if memory_block else []
    return {
        "plan": plan_dicts,
        "current_step": 0,
        "sources": [],
        "revision": 0,
        "trace": trace + [event("planner", "plan", _summary(plan_dicts))],
    }


def replan(state: AgentState) -> dict:
    plan, c = state["plan"], state["critique"]
    completed = "\n".join(f"{s['id']}. {s['goal']}\n   findings: {s['result'][:400]}" for s in plan)
    feedback = "\n".join(
        [f"Constraint violation: {x}" for x in c["constraint_violations"]]
        + [f"Missing: {x}" for x in c["missing_info"]]
        + [f"Issue: {x}" for x in c["issues"]]
        + [f"Failed check: {x['number']} cited {x['cited']}: {x['detail']}" for x in c.get("failed_checks", [])[:10]]
    )
    sources = "\n".join(f"[{s['id']}] {s['url']}" for s in state.get("sources", []))
    llm = get_llm("planner", schema=Plan, temperature=0)
    system = PLANNER_FIXUP_SYSTEM.format(today=date.today().isoformat(), max_steps=MAX_FIXUP_STEPS)
    human = f"Task: {state['task']}{_memory_block(state)}\n\nCompleted steps:\n{completed}\n\nCritic feedback:\n{feedback}\n\nKnown sources:\n{sources}"
    result: Plan = llm.invoke([SystemMessage(system), HumanMessage(human)])

    steps = result.steps[:MAX_FIXUP_STEPS] if result and result.steps else []
    if not steps:  # fall back to one step for the most important missing item
        need = (c["constraint_violations"] + c["missing_info"] + c["issues"] + [state["task"]])[0]
        steps = [PlanStep(goal=f"Resolve: {need}", search_query=state["task"][:80])]
    new = _as_dicts(steps, len(plan) + 1, "fixup")
    head = f"Fix-up steps for revision {state['revision']} (appended; {len(plan)} completed steps kept):"
    return {"plan": plan + new, "current_step": len(plan), "trace": [event("planner", "plan", head + "\n" + _summary(new))]}
