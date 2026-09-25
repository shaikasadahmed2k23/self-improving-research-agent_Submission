"""Run the research agent from the terminal with a live step-by-step trace.

Usage:  python cli.py "Compare the pricing of the top 3 vector databases" [--out report.md]
"""
import argparse
import sys
import textwrap
from pathlib import Path

from agent.graph import build_graph

LABELS = {
    "plan": "PLAN",
    "thought": "THINK",
    "action": "ACT",
    "observation": "OBSERVE",
    "result": "RESULT",
    "report": "REPORT",
    "error": "ERROR",
}


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
    for update in graph.stream({"task": task}, config={"recursion_limit": 50}, stream_mode="updates"):
        for _node, delta in update.items():
            for ev in (delta or {}).get("trace", []):
                print_event(ev)
            final.update(delta or {})

    report = final.get("draft", "")
    print("\n" + "=" * 80 + "\n" + report)
    if args.out and report:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(report, encoding="utf-8")
        print(f"Saved report to {args.out}")
    return 0 if report else 1


if __name__ == "__main__":
    sys.exit(main())
