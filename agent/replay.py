"""Replay recorded runs without LLM calls: JSONL traces from agent.runner, or CLI logs of older runs."""
import json
import re
from pathlib import Path

from agent import config
from agent.runner import LABELS

_HEADER = re.compile(r"^\[(\w+)\] ([A-Z]+)$")
_STEP = re.compile(r"^(\d+)\. (.*?)  \(search: (.*)\)$")
KIND_OF = {label: kind for kind, label in LABELS.items()}


def list_traces() -> list[Path]:
    """Recorded runs (data/traces) and committed demo traces (samples/traces), newest first."""
    paths = [p for d in (config.TRACES_DIR, config.SAMPLE_TRACES_DIR) if d.exists() for p in d.glob("*.jsonl")]
    return sorted(paths, key=lambda p: p.name, reverse=True)


def load_trace(path: Path) -> list[tuple[str, dict]]:
    with Path(path).open(encoding="utf-8") as f:
        return [(r["node"], r["delta"]) for r in map(json.loads, f) if r]


def _events(head: str) -> list[dict]:
    events, current = [], None
    for line in head.splitlines():
        m = _HEADER.match(line)
        if m and m.group(2) in KIND_OF:
            current = {"node": m.group(1), "kind": KIND_OF[m.group(2)], "lines": []}
            events.append(current)
        elif current is not None:
            current["lines"].append(line[4:] if line.startswith("    ") else line)
    return [{"node": e["node"], "kind": e["kind"], "content": "\n".join(e["lines"]).strip()} for e in events]


def from_cli_log(text: str) -> list[tuple[str, dict]]:
    """Rebuild a replayable update stream from a cli.py log (plan, step progress, trace, report, critic, tokens)."""
    head, _, tail = text.partition("\n" + "=" * 80 + "\n")
    task = re.search(r"^TASK: (.*)$", head, re.M)
    updates: list[tuple[str, dict]] = [("start", {"task": task.group(1) if task else "", "use_memory": "[recall]" in head})]
    plan: list[dict] = []
    for ev in _events(head):
        delta: dict = {"trace": [ev]}
        body = ev["content"]
        if ev["node"] == "planner" and ev["kind"] == "plan":
            fixup = body.startswith("Fix-up steps")
            for line in body.splitlines():
                if m := _STEP.match(line.strip()):
                    plan.append({"id": int(m.group(1)), "goal": m.group(2), "search_query": m.group(3), "status": "pending",
                                 "result": "", "origin": "fixup" if fixup else "initial"})
            delta.update(plan=[dict(s) for s in plan], current_step=len(plan) - sum(s["status"] == "pending" for s in plan))
        elif ev["kind"] == "result" and (m := re.match(r"Step (\d+) findings:\n?(.*)", body, re.S)):
            for s in plan:
                if s["id"] == int(m.group(1)):
                    s.update(status="done", result=m.group(2))
            delta.update(plan=[dict(s) for s in plan], current_step=int(m.group(1)))
        elif ev["kind"] == "critique" and (m := re.match(r"Score (\d+)/10 -> (\w+)", body)):
            delta["critique"] = {"score": int(m.group(1)), "verdict": m.group(2)}
        elif ev["kind"] == "lesson" and (m := re.search(r"Run #(\d+) saved", body)):
            delta["run_id"] = int(m.group(1))
        updates.append((ev["node"], delta))

    report, _, stats = tail.partition("\nCritic: ")
    final: dict = {"draft": report.strip() + "\n"}
    if m := re.match(r"(\d+)/10, verdict=(\w+), revisions=(\d+)", stats):
        final.update(critique={"score": int(m.group(1)), "verdict": m.group(2)}, revision=int(m.group(3)))
    updates.append(("final", final))
    tokens = {
        m.group(1): {"total_tokens": int(m.group(2).replace(",", "")), "input_tokens": int(m.group(3).replace(",", "")),
                     "output_tokens": int(m.group(4).replace(",", ""))}
        for m in re.finditer(r"^Tokens \[(.+?)\]: ([\d,]+) \(in ([\d,]+) / out ([\d,]+)\)", stats, re.M)
    }
    updates.append(("done", {"tokens": tokens}))
    return updates
