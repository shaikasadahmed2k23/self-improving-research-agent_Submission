"""Run the research agent from the terminal with a live step-by-step trace.

Usage:  python cli.py "Compare the pricing of the top 3 vector databases" [--out report.md]
"""
import argparse
import sys
import textwrap
from collections import Counter
from pathlib import Path

from langchain_core.callbacks import get_usage_metadata_callback

from agent.graph import build_graph

LABELS = {
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
APPEND_KEYS = {"trace", "tool_log", "calculations"}


def print_event(ev: dict) -> None:
    label = f"[{ev['node']}] {LABELS.get(ev['kind'], ev['kind'].upper())}"
    body = textwrap.indent(ev["content"].strip(), "    ")
    print(f"\n{label}\n{body}", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Self-improving research agent (CLI)")
    parser.add_argument("task", nargs="+", help="research task / question")
    parser.add_argument("--out", type=Path, help="also save the final report to this markdown file")
    args = parser.parse_args()
    task = " ".join(args.task)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    print(f"TASK: {task}")
    final: dict = {}
    graph = build_graph()
    with get_usage_metadata_callback() as usage:
        for update in graph.stream({"task": task}, config={"recursion_limit": 250}, stream_mode="updates"):
            for _node, delta in update.items():
                delta = delta or {}
                for ev in delta.get("trace", []):
                    print_event(ev)
                for key, value in delta.items():  # append-only state fields arrive as increments
                    final[key] = final.get(key, []) + value if key in APPEND_KEYS else value

    report = final.get("draft", "")
    print("\n" + "=" * 80 + "\n" + report)
    if final.get("critique"):
        c = final["critique"]
        print(f"Critic: {c['score']}/10, verdict={c['verdict']}, revisions={final.get('revision', 0)}")
    tools_used = Counter(t["tool"] for t in final.get("tool_log", []))
    print("Tools used: " + (", ".join(f"{k} x{v}" for k, v in tools_used.items()) or "none"))
    for model, u in usage.usage_metadata.items():
        print(f"Tokens [{model}]: {u['total_tokens']:,} (in {u['input_tokens']:,} / out {u['output_tokens']:,})")
    if args.out and report:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(report, encoding="utf-8")
        print(f"Saved report to {args.out}")
    return 0 if report else 1


if __name__ == "__main__":
    sys.exit(main())
