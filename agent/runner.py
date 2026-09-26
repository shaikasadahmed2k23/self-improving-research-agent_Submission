"""Run the agent as a stream of UI-friendly updates (shared by the CLI and the Streamlit app).

Each update is (node, delta) where delta holds only JSON-safe fields the UI needs. Every run is recorded as JSONL in
data/traces/ so it can be replayed later without any LLM calls (UI development, demos when quotas are exhausted).
"""
import json
import re
import time
from collections.abc import Iterable, Iterator
from pathlib import Path

from langchain_core.callbacks import get_usage_metadata_callback

from agent import config
from agent.memory.store import MemoryStore

UI_KEYS = ("trace", "plan", "current_step", "draft", "critique", "revision", "memory", "run_id", "report_path", "tool_log")
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


def _live(task: str, use_memory: bool) -> Iterator[tuple[str, dict]]:
    from agent.graph import build_graph  # heavy import; not needed for replays

    yield "start", {"task": task, "use_memory": use_memory}
    run_id = None
    with get_usage_metadata_callback() as usage:
        try:
            for update in build_graph(use_memory=use_memory).stream(
                {"task": task}, config={"recursion_limit": 250}, stream_mode="updates"
            ):
                for node, delta in update.items():
                    safe = {k: v for k, v in (delta or {}).items() if k in UI_KEYS}
                    run_id = safe.get("run_id", run_id)
                    if safe:
                        yield node, safe
        except Exception as exc:  # M6 will turn this into a graceful partial report
            yield "error", {"trace": [{"node": "runner", "kind": "error", "content": f"{type(exc).__name__}: {str(exc)[:500]}"}]}
            raise
        finally:
            tokens = {m: {k: u[k] for k in ("input_tokens", "output_tokens", "total_tokens")} for m, u in usage.usage_metadata.items()}
    if run_id:
        MemoryStore().set_run_tokens(run_id, sum(t["total_tokens"] for t in tokens.values()))
    yield "done", {"tokens": tokens}


def stream_run(task: str, *, use_memory: bool = True, record_trace: bool = True) -> Iterator[tuple[str, dict]]:
    """Run the agent live. Yields ("start", ...), (node, delta)..., ("done", {"tokens": {model: {...}}})."""
    updates = _live(task, use_memory)
    return record(_trace_path(task), updates) if record_trace else updates
