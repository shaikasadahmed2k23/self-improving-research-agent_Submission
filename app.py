"""Streamlit UI: live research runs with a step-by-step trace, recorded-run replay, and the agent's memory.

Run:  streamlit run app.py
"""
import time
from pathlib import Path

import pandas as pd
import streamlit as st

from agent import config
from agent.memory.store import MemoryStore
from agent.replay import list_traces, load_trace
from agent.runner import DEV_TASKS, LABELS, fold, stream_run

st.set_page_config(page_title="Self-Improving Research Agent", page_icon="🔎", layout="wide")

ICONS = {
    "memory": "🧠", "plan": "🗺️", "thought": "💭", "action": "🔧", "observation": "👁️", "result": "✅",
    "report": "📝", "check": "🔎", "critique": "⚖️", "lesson": "🎓", "error": "⚠️",
}
EXPANDED = {"memory", "plan", "check", "critique", "lesson", "error"}  # the events that tell the story
PLAIN = {"observation", "action", "thought"}  # raw text; markdown would mangle tool output


# ---------- rendering ------------------------------------------------------------------------------------------------

def render_event(box, ev: dict) -> None:
    label = LABELS.get(ev["kind"], ev["kind"].upper())
    lines = ev["content"].strip().splitlines()
    preview = lines[0][:90] if lines else ""
    with box.expander(f"{ICONS.get(ev['kind'], '•')} **{label}** · {ev['node']} — {preview}", expanded=ev["kind"] in EXPANDED):
        if ev["kind"] in PLAIN:
            st.text(ev["content"])
        else:
            st.markdown(ev["content"].replace("\n", "  \n"))


def render_plan(box, state: dict) -> None:
    with box.container():
        st.subheader("Plan")
        plan = state.get("plan", [])
        if not plan:
            st.caption("Waiting for the planner…")
        for i, s in enumerate(plan):
            if s["status"] == "done":
                icon = "✅"
            elif i == state.get("current_step") and not state.get("finished"):
                icon = "▶️"
            else:
                icon = "⬜"
            badge = " · *fix-up*" if s.get("origin") == "fixup" else ""
            st.markdown(f"{icon} **{s['id']}.** {s['goal']}{badge}")
        c = state.get("critique")
        if c:
            st.divider()
            cols = st.columns(3)
            cols[0].metric("Critic score", f"{c['score']}/10")
            cols[1].metric("Verdict", c["verdict"])
            cols[2].metric("Revisions", state.get("revision", 0))


def play(updates, delay: float = 0.0) -> dict:
    """Consume (node, delta) updates, rendering the plan and trace as they arrive; return the folded run state."""
    state: dict = {}
    left, right = st.columns([1, 2], gap="large")
    plan_box = left.empty()
    render_plan(plan_box, state)
    right.subheader("Trace")
    trace_box = right.container(height=620)
    for node, delta in updates:
        if node == "start":
            state.update(delta)
            continue
        if node == "done":
            state["tokens"] = delta.get("tokens", {})
            continue
        fold(state, delta)
        for ev in delta.get("trace", []):
            render_event(trace_box, ev)
        if {"plan", "current_step", "critique", "revision"} & delta.keys():
            render_plan(plan_box, state)
        if delay:
            time.sleep(delay)
    state["finished"] = True
    render_plan(plan_box, state)
    return state


def render_static(state: dict, kinds: list[str]) -> None:
    left, right = st.columns([1, 2], gap="large")
    render_plan(left, state)
    right.subheader("Trace")
    box = right.container(height=620)
    for ev in state.get("trace", []):
        if ev["kind"] in kinds:
            render_event(box, ev)


def render_stopped(stopped: dict) -> None:
    st.error(f"**Run stopped.** {stopped['message']}")
    if stopped["kind"] == "quota":
        st.info("👉 The free-tier quotas are exhausted for now (Groq quotas are rolling 24 h). Switch the sidebar **Mode** to "
                "**Replay a recorded run** to watch a complete recorded run step by step, or try again later. "
                "The findings gathered so far are below.")
    with st.expander("Error details"):
        st.code(stopped["detail"])


def render_result(state: dict) -> None:
    if state.get("stopped"):
        render_stopped(state["stopped"])
    report = state.get("draft", "")
    if not report:
        st.warning("The run ended without a report (see the ERROR events in the trace).")
        return
    st.divider()
    head = st.columns([3, 1])
    head[0].subheader("Partial report" if state.get("stopped") else "Final report")
    head[1].download_button("⬇️ Download report (.md)", report, file_name="research-report.md", mime="text/markdown")
    with st.container(border=True):
        st.markdown(report)
    tokens = state.get("tokens") or {}
    if tokens:
        total = sum(t["total_tokens"] for t in tokens.values())
        per_model = ", ".join(f"{m}: {t['total_tokens']:,}" for m, t in tokens.items())
        st.caption(f"Tokens: {total:,} ({per_model})")


# ---------- tabs -----------------------------------------------------------------------------------------------------

def research_tab(settings: dict) -> None:
    if settings["mode"] == "Live run":
        preset = st.selectbox("Example task", ["(write your own)"] + list(DEV_TASKS.values()))
        task = st.text_area("Research task", value="" if preset.startswith("(") else preset, height=80,
                            placeholder="e.g. Compare the pricing of the top 3 managed vector databases")
        start = st.button("▶️ Run research", type="primary", disabled=not task.strip())
        if start:
            with st.spinner("Researching… (each step is shown as it happens)"):
                try:
                    st.session_state["result"] = play(stream_run(task.strip(), use_memory=settings["use_memory"]))
                except Exception as exc:  # the runner already turns failures into a partial report; this is a last resort
                    st.session_state["result"] = {"stopped": {"kind": "error", "message": "The run crashed.",
                                                              "detail": f"{type(exc).__name__}: {str(exc)[:300]}"}}
            render_result(st.session_state["result"])
            return
    else:
        traces = list_traces()
        if not traces:
            st.info("No recorded runs yet. Every live run (CLI or UI) is saved to data/traces/.")
            return
        path = st.selectbox("Recorded run", traces, format_func=lambda p: p.stem)
        delay = st.slider("Replay speed (seconds per event)", 0.0, 1.0, 0.15, 0.05)
        if st.button("▶️ Replay", type="primary"):
            st.session_state["result"] = play(load_trace(path), delay)
            render_result(st.session_state["result"])
            return

    state = st.session_state.get("result")
    if state:  # after a rerun (e.g. the download button), show the last run statically
        kinds = st.multiselect("Show events", list(LABELS), default=list(LABELS), format_func=lambda k: LABELS[k])
        render_static(state, kinds)
        render_result(state)


def memory_tab() -> None:
    store = MemoryStore()
    runs, lessons, sources = store.runs(), store.lessons(), store.sources()
    st.caption(f"Database: {store.path}")
    cols = st.columns(3)
    cols[0].metric("Runs", len(runs))
    cols[1].metric("Lessons", len(lessons))
    cols[2].metric("Trusted sources", sum(1 for s in sources if s["verified"] > s["failed"] or s["suggested"]))
    if not runs:
        st.info("No runs yet. Run a task with memory on; the reflect step stores lessons and trusted sources here.")
        return

    df = pd.DataFrame(runs)
    df["run"] = "#" + df["id"].astype(str)
    left, right = st.columns(2)
    with left:
        st.markdown("**Critic score and revisions per run**")
        st.line_chart(df.set_index("run")[["score", "revisions"]], y_label="score / revisions")
    with right:
        st.markdown("**Tokens per run**")
        st.bar_chart(df.set_index("run")[["tokens"]].fillna(0), y_label="tokens")

    st.markdown("#### Lessons")
    st.caption("Learned by the reflect step from the critic's findings; injected into the planner prompt of similar tasks.")
    if lessons:
        st.dataframe(pd.DataFrame(lessons)[["id", "category", "text", "keywords", "times_seen", "times_used", "times_helpful"]],
                     hide_index=True, width="stretch")
    st.markdown("#### Trusted sources")
    st.caption("URL-level trust from the deterministic citation check. *suggested* = named by reflection, not verified yet.")
    if sources:
        sdf = pd.DataFrame(sources)
        sdf["status"] = sdf.apply(lambda s: "verified" if s["verified"] > s["failed"] else ("suggested" if s["suggested"] else "untrusted"), axis=1)
        st.dataframe(sdf[["url", "status", "verified", "failed", "fetched", "facts"]], hide_index=True, width="stretch")
    st.markdown("#### Runs")
    st.dataframe(df[["id", "created_at", "task", "score", "verdict", "revisions", "tokens", "report_path"]],
                 hide_index=True, width="stretch")


def sidebar() -> dict:
    with st.sidebar:
        st.header("🔎 Research agent")
        st.caption("Plan → ReAct research → cited report → critic → reflect. Learns lessons and trusted sources per run.")
        mode = st.radio("Mode", ["Live run", "Replay a recorded run"],
                        help="Replays a saved trace step by step without any LLM calls.")
        use_memory = st.toggle("Memory on (recall + reflect)", value=True,
                               help="Off: no lessons or trusted sources are read before planning, and nothing is saved.")
        dbs = sorted({Path(config.MEMORY_DB_PATH), *config.DATA_DIR.glob("*.db")})
        db = st.selectbox("Memory database", dbs, index=dbs.index(Path(config.MEMORY_DB_PATH)), format_func=lambda p: p.name)
        config.MEMORY_DB_PATH = Path(db)  # single-user demo app: recall/reflect read this at call time
        st.divider()
        st.caption(
            f"Executor: `{config.groq_model_for('executor')}`  \nCritic: `{config.groq_model_for('critic')}`  \n"
            f"Token saver: {'on' if config.TOKEN_SAVER else 'off'} · fallbacks: {'on' if config.LLM_FALLBACKS else 'off'}"
        )
    return {"mode": mode, "use_memory": use_memory}


def main() -> None:
    settings = sidebar()
    st.title("Self-Improving Research Agent")
    research, memory = st.tabs(["Research", "Memory"])
    with research:
        research_tab(settings)
    with memory:
        memory_tab()


main()
