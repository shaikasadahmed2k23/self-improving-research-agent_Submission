"""Critic node: LLM review (always the strong model) + routing decision with a revision cap."""
from collections import Counter

from langchain_core.messages import HumanMessage, SystemMessage

from agent import config
from agent.llm import get_llm
from agent.prompts import CRITIC_HUMAN, CRITIC_SYSTEM
from agent.state import AgentState, Critique, event
from agent.verification import FAIL_STATUSES, domain, summarize_checks


def _tool_log_summary(tool_log: list[dict]) -> str:
    if not tool_log:
        return "(no tools were called)"
    counts = Counter(t["tool"] for t in tool_log)
    lines = ["Tool calls: " + ", ".join(f"{name} x{n}" for name, n in counts.items())]
    for tool in ("fetch_page", "calculator"):
        if tool not in counts:
            lines.append(f"{tool}: NEVER called")
    for t in tool_log:
        if t["tool"] != "web_search":
            arg = next(iter(t["args"].values()), "")
            lines.append(f"- step {t['step']}: {t['tool']}({arg}){' -> ERROR' if t['error'] else ''}")
    return "\n".join(lines)


def _sources_summary(sources: list[dict]) -> str:
    return "\n".join(
        f"[{s['id']}] {domain(s['url'])} ({'fetched page' if s.get('provider') == 'fetch' else 'search snippet'}): {s['title'][:80]}"
        for s in sources
    ) or "(none)"


def _critique_text(c: dict, revision: int) -> str:
    lines = [f"Score {c['score']}/10 -> {c['verdict']}"]
    for label, key in (("Constraint violations", "constraint_violations"), ("Issues", "issues"), ("Missing info", "missing_info")):
        if c[key]:
            lines.append(f"{label}:")
            lines += [f"  - {x}" for x in c[key]]
    if c["final"]:
        lines.append("Accepted." if c["verdict"] == "accept" else f"Revision limit ({config.MAX_REVISIONS}) reached: delivering with reviewer notes.")
    else:
        lines.append(f"Sending back for revision {revision}/{config.MAX_REVISIONS}.")
    return "\n".join(lines)


def critic(state: AgentState) -> dict:
    checks = state.get("checks", [])
    llm = get_llm("critic", schema=Critique, temperature=0)
    human = CRITIC_HUMAN.format(
        task=state["task"],
        tool_log=_tool_log_summary(state.get("tool_log", [])),
        sources=_sources_summary(state.get("sources", [])),
        checks=summarize_checks(checks, max_lines=25),
        draft=state["draft_raw"],
    )
    result: Critique = llm.invoke([SystemMessage(CRITIC_SYSTEM.format(pass_score=config.CRITIC_PASS_SCORE)), HumanMessage(human)])
    c = result.model_dump()
    c["score"] = max(1, min(10, int(c["score"])))

    # Guardrails: the verdict must be consistent with the evidence.
    if c["verdict"] == "accept" and c["constraint_violations"]:
        c["verdict"] = "needs_research"
    elif c["verdict"] == "accept" and c["score"] < config.CRITIC_PASS_SCORE:
        c["verdict"] = "needs_rewrite"
    c["failed_checks"] = [ch for ch in checks if ch["status"] in FAIL_STATUSES]

    revision = state.get("revision", 0)
    c["final"] = c["verdict"] == "accept" or revision >= config.MAX_REVISIONS
    if not c["final"]:
        revision += 1

    update = {"critique": c, "critiques": [c], "revision": revision, "trace": [event("critic", "critique", _critique_text(c, revision))]}
    if c["final"] and c["verdict"] != "accept":
        notes = c["constraint_violations"] + c["issues"] + [f"Missing: {m}" for m in c["missing_info"]]
        update["draft"] = state["draft"].rstrip() + "\n\n## Reviewer notes (unresolved)\n" + "\n".join(f"- {n}" for n in notes) + "\n"
    return update


def route_after_critic(state: AgentState) -> str:
    c = state["critique"]
    if c["final"]:
        return "end"
    return "planner" if c["verdict"] == "needs_research" else "writer"
