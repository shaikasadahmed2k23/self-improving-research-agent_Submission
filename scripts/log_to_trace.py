"""Convert a cli.py log (runs recorded before traces existed) into a replayable JSONL trace.

Usage:  python scripts/log_to_trace.py run.log samples/traces/name.jsonl
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.replay import from_cli_log  # noqa: E402
from agent.runner import record  # noqa: E402

if __name__ == "__main__":
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    n = sum(1 for _ in record(dst, from_cli_log(src.read_text(encoding="utf-8"))))
    print(f"{n} updates -> {dst}")
