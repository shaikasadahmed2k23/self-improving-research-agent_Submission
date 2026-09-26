"""Reflect node: learn from the finished run and persist it.

1. Source trust (deterministic): every cited URL gets verified/failed counts from the final citation check.
2. Lessons (one 20B call): extracted from the full critique history; skipped when the first draft passed cleanly.
   The same call names pages a lesson refers to (e.g. the official pricing page that was never fetched); each is
   stored as a *suggested* source only if fetch_page can read it, and becomes trusted once a later run verifies it.
3. Lesson feedback: lessons injected into this run count as helpful if it was accepted with 0 revisions.
4. The run and its report file are saved.
"""
import logging
import re
from datetime import date

from langchain_core.messages import HumanMessage, SystemMessage

from agent import config
from agent.llm import get_llm
from agent.memory.store import MemoryStore
from agent.nodes.critic import _tool_log_summary
from agent.nodes.writer import cited_ids
from agent.prompts import REFLECT_HUMAN, REFLECT_SYSTEM
from agent.state import AgentState, Reflection, event
from agent.tools.fetch import fetch_page
from agent.tools.registry import canonical_url
from agent.verification import FAIL_STATUSES, domain

log = logging.getLogger(__name__)
MAX_LESSONS = 3
MAX_SUGGESTED = 2


def source_outcomes(draft_raw: str, sources: list[dict], checks: list[dict]) -> list[dict]:
    """Per cited source: how many numbers it verified / failed in the final draft, and which ones."""
    by_id = {s["id"]: s for s in sources}
    stats = {i: {"verified": 0, "failed": 0, "facts": []} for i in cited_ids(draft_raw) if i in by_id}
    for c in checks:
        if c["status"] == "verified":
            for i in c.get("verified_in", []):
                if i in stats:
                    stats[i]["verified"] += 1
                    stats[i]["facts"].append(c["number"])
        elif c["status"] in FAIL_STATUSES:
            for i in c["cited"]:
                if i in stats:
                    stats[i]["failed"] += 1
    return [
        {
            "key": canonical_url(by_id[i]["url"]),
            "url": by_id[i]["url"],
            "domain": domain(by_id[i]["url"]),
            "title": by_id[i].get("title", ""),
            "fetched": by_id[i].get("provider") == "fetch",
            **st,
            "facts": list(dict.fromkeys(st["facts"])),
        }
        for i, st in stats.items()
    ]


def _had_problems(critiques: list[dict]) -> bool:
    return any(
        c["verdict"] != "accept" or c["constraint_violations"] or c["issues"] or c.get("failed_checks") for c in critiques
    )


def _history(critiques: list[dict]) -> str:
    blocks = []
    for n, c in enumerate(critiques):
        lines = [f"Revision {n}: score {c['score']}/10, verdict {c['verdict']}"]
        lines += [f"  constraint violation: {x}" for x in c["constraint_violations"]]
        lines += [f"  issue: {x}" for x in c["issues"]]
        lines += [f"  missing: {x}" for x in c["missing_info"]]
        lines += [f"  failed check: {x['number']} cited {x['cited']}: {x['status']}" for x in c.get("failed_checks", [])[:6]]
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def extract_lessons(state: AgentState) -> Reflection:
    critiques = state.get("critiques", [])
    final = state["critique"]
    fixups = [s["goal"] for s in state["plan"] if s.get("origin") == "fixup"]
    outcome = f"final score {final['score']}/10, verdict {final['verdict']}, after {state.get('revision', 0)} revision(s)"
    seen = "\n".join(
        f"- {s['url']} ({'fetched' if s.get('provider') == 'fetch' else 'search snippet only'})" for s in state.get("sources", [])
    )
    human = REFLECT_HUMAN.format(
        task=state["task"],
        tool_log=_tool_log_summary(state.get("tool_log", [])),
        sources=seen or "(none)",
        history=_history(critiques),
        fixups="\n".join(f"- {g}" for g in fixups) or "(none)",
        outcome=outcome,
    )
    result: Reflection = get_llm("reflect", schema=Reflection, temperature=0).invoke(
        [SystemMessage(REFLECT_SYSTEM), HumanMessage(human)]
    )
    return result or Reflection()


def suggested_sources(urls: list[str], known_keys: set[str]) -> list[dict]:
    """Pages reflection says to use, kept only if fetch_page can actually read them (guards against invented URLs)."""
    out = []
    for url in dict.fromkeys(u.strip() for u in urls):
        key = canonical_url(url)
        if not url.startswith(("http://", "https://")) or key in known_keys or len(out) >= MAX_SUGGESTED:
            continue
        try:
            page = fetch_page(url)
        except Exception as exc:
            log.info("Suggested source %s not stored: %s", url, exc)
            continue
        out.append({"key": key, "url": url, "domain": domain(url), "title": page["title"], "fetched": False,
                    "verified": 0, "failed": 0, "facts": [], "suggested": True})
        known_keys.add(key)
    return out


def save_report(task: str, report: str, suffix: str = "") -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", task.lower()).strip("-")[:60] or "report"
    path = config.REPORTS_DIR / f"{date.today().isoformat()}-{slug}{suffix}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report, encoding="utf-8")
    return str(path.relative_to(config.ROOT_DIR)) if path.is_relative_to(config.ROOT_DIR) else str(path)


def reflect(state: AgentState) -> dict:
    store = MemoryStore()
    final = state["critique"]
    revisions = state.get("revision", 0)
    report_path = save_report(state["task"], state.get("draft", ""))
    run_id = store.save_run(state["task"], final["score"], final["verdict"], revisions, report_path)

    outcomes = source_outcomes(state.get("draft_raw", ""), state.get("sources", []), state.get("checks", []))
    store.record_sources(run_id, outcomes)
    trusted = [o for o in outcomes if o["verified"] > o["failed"]]

    used = [l["id"] for l in (state.get("memory") or {}).get("lessons", [])]
    helpful = final["verdict"] == "accept" and revisions == 0
    store.mark_lessons_used(run_id, used, helpful)

    lines = [f"Run #{run_id} saved (score {final['score']}/10, {revisions} revision(s)); report: {report_path}"]
    if used:
        lines.append(f"{len(used)} recalled lesson(s) marked {'helpful' if helpful else 'used (not yet helpful)'}.")
    lines.append(
        "Trusted sources: " + (", ".join(f"{o['url']} ({o['verified']} verified)" for o in trusted) or "none this run")
    )
    if _had_problems(state.get("critiques", [])):
        reflection = extract_lessons(state)
        for lesson in reflection.lessons[:MAX_LESSONS]:
            _, is_new = store.add_lesson(run_id, lesson.text, lesson.category, lesson.keywords)
            lines.append(f"{'New lesson' if is_new else 'Lesson seen again'} [{lesson.category}]: {lesson.text}")
        suggested = suggested_sources(reflection.source_urls, {o["key"] for o in trusted})
        store.record_sources(run_id, suggested)
        lines += [f"Suggested source (reachable, not verified yet): {s['url']}" for s in suggested]
    else:
        lines.append("First draft passed cleanly: no new lessons.")
    return {"run_id": run_id, "report_path": report_path, "trace": [event("reflect", "lesson", "\n".join(lines))]}
