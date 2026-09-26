"""Print what the agent has learned: runs, lessons and trusted sources.

Usage:  python scripts/show_memory.py [--db path]
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.memory.store import MemoryStore  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, help="memory database (default: MEMORY_DB_PATH)")
    store = MemoryStore(parser.parse_args().db)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    print(f"Memory: {store.path}\n\nRUNS")
    for r in store.runs():
        tokens = f"{r['tokens']:,}" if r["tokens"] else "?"
        print(f"  #{r['id']} {r['created_at']}  score {r['score']}  {r['verdict']}  revisions {r['revisions']}  tokens {tokens}")
        print(f"      {r['task']}")
    print("\nLESSONS (seen / used / helpful)")
    for l in store.lessons():
        print(f"  #{l['id']} [{l['category']}] {l['times_seen']}/{l['times_used']}/{l['times_helpful']}  {l['text']}")
        print(f"      keywords: {l['keywords']}")
    print("\nSOURCES (verified / failed)")
    for s in store.sources():
        fetched = "fetched" if s["fetched"] else ("suggested" if s["suggested"] and not s["verified"] else "snippet")
        print(f"  {s['verified']}/{s['failed']}  {fetched}  {s['url']}  facts: {', '.join(json.loads(s['facts']))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
