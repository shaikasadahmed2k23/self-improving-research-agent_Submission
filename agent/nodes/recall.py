"""Recall node: look up lessons and trusted sources from similar past runs (SQLite, no LLM call)."""
from agent.memory.store import MemoryStore
from agent.state import AgentState, event


def format_lessons(memory: dict) -> str:
    return "\n".join(f"- {l['text']}" for l in memory.get("lessons", [])) or "(none)"


def format_sources(memory: dict) -> str:
    lines = []
    for s in memory.get("trusted_sources", []):
        if s["verified"]:
            kind = "fetched page" if s["fetched"] else "search result"
        else:
            kind = "suggested by reflection on a past run; not verified yet: fetch_page it"
        facts = f"; verified: {', '.join(s['facts'][:4])}" if s["facts"] else ""
        lines.append(f"- {s['url']} ({kind}{facts})")
    return "\n".join(lines) or "(none)"


def has_memory(memory: dict | None) -> bool:
    return bool(memory and (memory.get("lessons") or memory.get("trusted_sources")))


def recall(state: AgentState) -> dict:
    memory = MemoryStore().recall(state["task"])
    runs = memory["similar_runs"]
    if not has_memory(memory):
        text = f"No lessons or trusted sources yet ({len(runs)} similar past run(s))."
    else:
        past = "; ".join(f"#{r['id']} score {r['score']}, {r['revisions']} revision(s)" for r in runs)
        text = (
            f"{len(runs)} similar past run(s): {past}\n"
            f"Lessons:\n{format_lessons(memory)}\nTrusted sources:\n{format_sources(memory)}"
        )
    return {"memory": memory, "trace": [event("recall", "memory", text)]}
