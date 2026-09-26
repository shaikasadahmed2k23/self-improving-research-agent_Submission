"""Run the research agent from the terminal with a live step-by-step trace.

Usage:  python cli.py "Compare the pricing of the top 3 vector databases" [--out report.md]
        python cli.py --dev 2        # short preset test task (pair with TOKEN_SAVER=true while developing)
Every run is also recorded to data/traces/*.jsonl for replay in the Streamlit app.
"""
import argparse
import sys
import textwrap
from collections import Counter
from pathlib import Path

from agent import config
from agent.runner import DEV_TASKS, LABELS, fold, stream_run


def print_event(ev: dict) -> None:
    label = f"[{ev['node']}] {LABELS.get(ev['kind'], ev['kind'].upper())}"
    body = textwrap.indent(ev["content"].strip(), "    ")
    print(f"\n{label}\n{body}", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Self-improving research agent (CLI)")
    parser.add_argument("task", nargs="*", help="research task / question")
    parser.add_argument("--dev", type=int, choices=sorted(DEV_TASKS), help="run a short preset test task instead")
    parser.add_argument("--no-memory", action="store_true", help="skip recall and reflect (no lessons read or saved)")
    parser.add_argument("--out", type=Path, help="also save the final report to this markdown file")
    args = parser.parse_args()
    if bool(args.task) == bool(args.dev):
        parser.error("give either a task or --dev N")
    task = DEV_TASKS[args.dev] if args.dev else " ".join(args.task)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    print(f"TASK: {task}")
    if config.TOKEN_SAVER:
        print(
            f"TOKEN_SAVER on: <= {config.MAX_PLAN_STEPS} steps, {config.MAX_REACT_ITERATIONS} LLM calls/step, "
            f"{config.MAX_REVISIONS} revision(s), pages {config.PAGE_CHAR_LIMIT} chars, "
            f"{config.SEARCH_MAX_RESULTS} results x {config.SNIPPET_CHARS} chars"
        )
    final: dict = {}
    for node, delta in stream_run(task, use_memory=not args.no_memory):
        for ev in delta.get("trace", []):
            print_event(ev)
        if node == "done":
            final["tokens"] = delta["tokens"]
        elif node != "start":
            fold(final, delta)

    report = final.get("draft", "")
    print("\n" + "=" * 80 + "\n" + report)
    if final.get("critique"):
        c = final["critique"]
        print(f"Critic: {c['score']}/10, verdict={c['verdict']}, revisions={final.get('revision', 0)}")
    tools_used = Counter(t["tool"] for t in final.get("tool_log", []))
    print("Tools used: " + (", ".join(f"{k} x{v}" for k, v in tools_used.items()) or "none"))
    for model, u in final["tokens"].items():
        print(f"Tokens [{model}]: {u['total_tokens']:,} (in {u['input_tokens']:,} / out {u['output_tokens']:,})")
    print(f"Tokens total: {sum(u['total_tokens'] for u in final['tokens'].values()):,}")
    if final.get("run_id"):
        print(f"Memory: run #{final['run_id']} saved; report at {final.get('report_path')}")
    if final.get("stopped"):
        s = final["stopped"]
        print(f"\nRUN STOPPED ({s['kind']}): {s['message']}\n  {s['detail']}\n"
              f"  Partial report saved to {final.get('report_path')}; the trace is in data/traces/.")
        if s["kind"] == "quota":
            print("  Try again later (Groq quotas are rolling 24h), or replay a recorded run in the UI.")
    if args.out and report:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(report, encoding="utf-8")
        print(f"Saved report to {args.out}")
    return 2 if final.get("stopped") else (0 if report else 1)


if __name__ == "__main__":
    sys.exit(main())
