"""Planner node: turn the task into an ordered list of research steps."""
from datetime import date

from langchain_core.messages import HumanMessage, SystemMessage

from agent import config
from agent.llm import get_llm
from agent.prompts import PLANNER_SYSTEM
from agent.state import AgentState, Plan, PlanStep, event


def planner(state: AgentState) -> dict:
    task = state["task"]
    llm = get_llm("planner", schema=Plan, temperature=0)
    system = PLANNER_SYSTEM.format(today=date.today().isoformat(), min_steps=1, max_steps=config.MAX_PLAN_STEPS)
    plan: Plan = llm.invoke([SystemMessage(system), HumanMessage(f"Research task: {task}")])

    steps = plan.steps[: config.MAX_PLAN_STEPS] if plan and plan.steps else []
    if not steps:  # degenerate output: fall back to a single direct search
        steps = [PlanStep(goal=task, search_query=task)]

    plan_dicts = [
        {"id": i + 1, "goal": s.goal, "search_query": s.search_query, "status": "pending", "result": ""}
        for i, s in enumerate(steps)
    ]
    summary = "\n".join(f"{s['id']}. {s['goal']}  (search: {s['search_query']})" for s in plan_dicts)
    return {"plan": plan_dicts, "current_step": 0, "sources": [], "trace": [event("planner", "plan", summary)]}
