"""Writer node: synthesize step findings into a cited markdown report."""
import re
from datetime import date

from langchain_core.messages import HumanMessage, SystemMessage

from agent.llm import get_llm, text_of
from agent.prompts import WRITER_SYSTEM
from agent.state import AgentState, event

_CITATION = re.compile(r"\[(\d+(?:\s*[,;]\s*\d+)*)\]")
_SOURCES_HEADING = re.compile(r"\n#{1,6}\s*(sources|references)\b.*", re.IGNORECASE | re.DOTALL)


def normalize_citations(text: str) -> str:
    """gpt-oss sometimes emits fullwidth 【3】 brackets; convert them to [3]."""
    return re.sub(r"【\s*(\d+(?:\s*[,;]\s*\d+)*)\s*】", r"[\1]", text)


def cited_ids(text: str) -> list[int]:
    ids = set()
    for group in _CITATION.findall(text):
        ids.update(int(n) for n in re.split(r"[,;]", group))
    return sorted(ids)


def append_sources(report: str, sources: list[dict]) -> str:
    """Replace any LLM-written source list with one built from real, cited URLs."""
    report = _SOURCES_HEADING.sub("", report).rstrip()
    by_id = {s["id"]: s for s in sources}
    lines = [f"{i}. [{by_id[i]['title'] or by_id[i]['url']}]({by_id[i]['url']})" for i in cited_ids(report) if i in by_id]
    return report + ("\n\n## Sources\n" + "\n".join(lines) if lines else "") + "\n"


def writer(state: AgentState) -> dict:
    findings = "\n\n".join(f"### Step {s['id']}: {s['goal']}\n{s['result']}" for s in state["plan"])
    llm = get_llm("writer", temperature=0.3)
    msg = llm.invoke(
        [
            SystemMessage(WRITER_SYSTEM.format(today=date.today().isoformat())),
            HumanMessage(f"Task: {state['task']}\n\nStep findings:\n{findings}"),
        ]
    )
    report = append_sources(normalize_citations(text_of(msg)), state.get("sources", []))
    n_cited = len(cited_ids(report.split("## Sources")[0]))
    return {"draft": report, "trace": [event("writer", "report", f"Draft written ({len(report)} chars, {n_cited} sources cited)")]}
