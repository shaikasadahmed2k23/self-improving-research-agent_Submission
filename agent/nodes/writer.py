"""Writer node: synthesize step findings into a cited markdown report."""
import re
from datetime import date

from langchain_core.messages import HumanMessage, SystemMessage

from agent.llm import get_llm, text_of
from agent.prompts import WRITER_REVISION, WRITER_SYSTEM
from agent.state import AgentState, event

_CITATION = re.compile(r"\[(\d+(?:\s*[,;]\s*\d+)*)\]")
_SOURCES_HEADING = re.compile(r"\n#{1,6}\s*(sources|references)\b.*", re.IGNORECASE | re.DOTALL)


def normalize_citations(text: str) -> str:
    """gpt-oss emits its native citation formats 【3】, 【3†L10-L12】 or [3†source]; convert them to [3]."""
    text = re.sub(r"【\s*(\d+(?:\s*[,;]\s*\d+)*)\s*(?:†[^】]*)?】", r"[\1]", text)
    return re.sub(r"\[\s*(\d+)\s*†[^\]]*\]", r"[\1]", text)


def _ids(group: str) -> list[int]:
    return [int(n) for n in re.split(r"[,;]", group)]


def cited_ids(text: str) -> list[int]:
    """Cited source ids in order of first appearance."""
    seen: list[int] = []
    for group in _CITATION.findall(text):
        seen.extend(i for i in _ids(group) if i not in seen)
    return seen


def finalize_citations(report: str, sources: list[dict]) -> str:
    """Renumber citations 1..n by first appearance, drop unknown ids, append a real Sources list.

    Any Sources/References section the LLM wrote is replaced by one built from actual URLs.
    """
    report = _SOURCES_HEADING.sub("", normalize_citations(report)).rstrip()
    by_id = {s["id"]: s for s in sources}
    order = [i for i in cited_ids(report) if i in by_id]
    new_id = {old: new for new, old in enumerate(order, start=1)}

    def renumber(match: re.Match) -> str:
        ids = sorted({new_id[i] for i in _ids(match.group(1)) if i in new_id})
        return "[" + ", ".join(map(str, ids)) + "]" if ids else ""

    report = _CITATION.sub(renumber, report)
    lines = [f"{new_id[i]}. [{by_id[i]['title'] or by_id[i]['url']}]({by_id[i]['url']})" for i in order]
    return report + ("\n\n## Sources\n" + "\n".join(lines) if lines else "") + "\n"


def _revision_request(state: AgentState) -> str:
    c = state["critique"]
    issues = c["constraint_violations"] + c["issues"] + [f"Missing: {m}" for m in c["missing_info"]]
    failed = [f"- {x['number']} cited {x['cited']}: {x['status']}, {x['detail']}" for x in c.get("failed_checks", [])[:15]]
    return WRITER_REVISION.format(
        issues="\n".join(f"- {i}" for i in issues) or "(none)",
        failed_checks="\n".join(failed) or "(none)",
        previous=state["draft_raw"],
    )


def writer(state: AgentState) -> dict:
    findings = "\n\n".join(f"### Step {s['id']}: {s['goal']}\n{s['result']}" for s in state["plan"])
    human = f"Task: {state['task']}\n\nStep findings:\n{findings}"
    lessons = (state.get("memory") or {}).get("lessons")
    if lessons:  # categories from reflection are unreliable, so the writer sees all recalled lessons (at most 5 lines)
        human += "\n\nLessons from past runs (apply those about writing and citing):\n" + "\n".join(f"- {l['text']}" for l in lessons)
    revising = state.get("revision", 0) > 0 and state.get("critique")
    if revising:
        human += _revision_request(state)

    llm = get_llm("writer", temperature=0.3)
    msg = llm.invoke([SystemMessage(WRITER_SYSTEM.format(today=date.today().isoformat())), HumanMessage(human)])

    draft_raw = _SOURCES_HEADING.sub("", normalize_citations(text_of(msg))).rstrip()
    report = finalize_citations(draft_raw, state.get("sources", []))
    n_cited = len(cited_ids(report.split("\n## Sources\n")[0]))
    label = f"Revised draft (revision {state['revision']})" if revising else "Draft written"
    return {
        "draft_raw": draft_raw,
        "draft": report,
        "trace": [event("writer", "report", f"{label} ({len(report)} chars, {n_cited} sources cited)")],
    }
