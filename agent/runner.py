"""Run the agent as a stream of UI-friendly updates (shared by the CLI and the Streamlit app).

Each update is (node, delta) where delta holds only JSON-safe fields the UI needs. Every run is recorded as JSONL in
data/traces/ so it can be replayed later without any LLM calls (UI development, demos when quotas are exhausted).
"""
import json
import logging
import re
import time
from collections.abc import Iterable, Iterator
from pathlib import Path

from langchain_core.callbacks import get_usage_metadata_callback

from agent import config
from agent.memory.store import MemoryStore

log = logging.getLogger(__name__)

UI_KEYS = ("trace", "plan", "current_step", "draft", "critique", "revision", "memory", "run_id", "report_path", "tool_log",
           "sources", "stopped")
APPEND_KEYS = {"trace", "tool_log"}
LABELS = {
    "memory": "MEMORY",
    "lesson": "LEARN",
    "plan": "PLAN",
    "thought": "THINK",
    "action": "ACT",
    "observation": "OBSERVE",
    "result": "RESULT",
    "report": "REPORT",
    "check": "VERIFY",
    "critique": "CRITIQUE",
    "error": "ERROR",
}
# Short, cheap tasks for development runs; each still exercises a different path through the agent.
DEV_TASKS = {
    1: "What is the monthly minimum spend on Pinecone's Standard plan?",  # single fact
    2: "Using Pinecone's official pricing page, what would 10 GB of storage cost per month on the Standard plan?",  # fetch + calculator
    3: "Compare the free tiers of Pinecone and Qdrant Cloud.",  # small comparison
    4: "Using Pinecone's official pricing page, what would 25 GB of storage cost per month on the Standard plan?",  # like 2: memory test
}


def fold(state: dict, delta: dict) -> dict:
    """Merge one update into the accumulated run state (append-only fields are extended)."""
    for key, value in delta.items():
        state[key] = state.get(key, []) + value if key in APPEND_KEYS else value
    return state


def _trace_path(task: str) -> Path:
    slug = re.sub(r"[^a-z0-9]+", "-", task.lower()).strip("-")[:50] or "run"
    return config.TRACES_DIR / f"{time.strftime('%Y%m%d-%H%M%S')}-{slug}.jsonl"


def record(path: Path, updates: Iterable[tuple[str, dict]]) -> Iterator[tuple[str, dict]]:
    """Pass updates through while appending each one to a JSONL file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for node, delta in updates:
            f.write(json.dumps({"node": node, "delta": delta}, ensure_ascii=False) + "\n")
            f.flush()
            yield node, delta


def _ui_safe(delta: dict) -> dict:
    safe = {k: v for k, v in (delta or {}).items() if k in UI_KEYS}
    if "sources" in safe:  # page text can be 20k chars per source; the UI and partial reports need only the list
        safe["sources"] = [{"id": s["id"], "title": s.get("title", ""), "url": s["url"]} for s in safe["sources"]]
    return safe


def stop_info(exc: BaseException) -> dict:
    """Classify why a run stopped, with a message for people (CLI and UI)."""
    from agent.llm import is_rate_limit

    detail = f"{type(exc).__name__}: {str(exc)[:300]}"
    if is_rate_limit(exc):
        return {"kind": "quota", "detail": detail,
                "message": "Every language model in the fallback chain is out of free-tier quota or rate-limited right now."}
    return {"kind": "error", "detail": detail, "message": "The run stopped because of an unexpected error."}


def partial_report(state: dict, stopped: dict) -> str:
    """Best report possible from a run that stopped early: the last draft if there is one, else the finished step findings."""
    from agent.nodes.writer import finalize_citations

    note = (f"> **Partial report.** {stopped['message']} What follows was gathered before the run stopped and was not (fully) "
            "reviewed by the critic.\n")
    if state.get("draft"):
        return note + "\n" + state["draft"]
    plan = state.get("plan", [])
    done = [s for s in plan if s["status"] == "done"]
    lines = [f"# Partial findings: {state.get('task', '')}", "", note]
    for s in done:
        lines += [f"## Step {s['id']}: {s['goal']}", s["result"], ""]
    if not done:
        lines.append("No research step finished before the run stopped.")
    pending = [s for s in plan if s["status"] != "done"]
    if pending:
        lines += ["", "## Not researched yet"] + [f"- {s['goal']}" for s in pending]
    return finalize_citations("\n".join(lines), state.get("sources", []))


def _live(task: str, use_memory: bool) -> Iterator[tuple[str, dict]]:
    from agent.graph import build_graph  # heavy import; not needed for replays
    from agent.nodes.reflect import save_report

    yield "start", {"task": task, "use_memory": use_memory}
    state: dict = {"task": task}
    with get_usage_metadata_callback() as usage:
        try:
            for update in build_graph(use_memory=use_memory).stream(
                {"task": task}, config={"recursion_limit": 250}, stream_mode="updates"
            ):
                for node, delta in update.items():
                    safe = _ui_safe(delta)
                    if safe:
                        fold(state, safe)
                        yield node, safe
        except Exception as exc:  # e.g. every model out of quota: keep the work instead of crashing
            log.exception("Run stopped")
            stopped = stop_info(exc)
            report = partial_report(state, stopped)
            path = save_report(task, report, suffix="-partial")
            yield "stopped", {
                "stopped": stopped,
                "draft": report,
                "report_path": path,
                "trace": [{"node": "runner", "kind": "error", "content": f"{stopped['message']}\n{stopped['detail']}\n"
                                                                         f"Partial report saved to {path}."}],
            }
        tokens = {m: {k: u[k] for k in ("input_tokens", "output_tokens", "total_tokens")} for m, u in usage.usage_metadata.items()}
    if state.get("run_id"):
        MemoryStore().set_run_tokens(state["run_id"], sum(t["total_tokens"] for t in tokens.values()))
    yield "done", {"tokens": tokens}


def stream_run(task: str, *, use_memory: bool = True, record_trace: bool = True) -> Iterator[tuple[str, dict]]:
    """Run the agent live. Yields ("start", ...), (node, delta)..., then ("stopped", {...}) if the run failed (quota,
    errors: a partial report is saved, nothing is raised), and finally ("done", {"tokens": {model: {...}}})."""
    updates = _live(task, use_memory)
    return record(_trace_path(task), updates) if record_trace else updates
