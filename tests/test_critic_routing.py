import pytest

from agent import config
from agent.nodes import critic as critic_mod
from agent.state import Critique


def _state(revision: int) -> dict:
    return {
        "task": "Using the official pricing page, find X",
        "draft_raw": "X costs $5 [1].",
        "draft": "X costs $5 [1].\n\n## Sources\n1. [a](https://a.io)\n",
        "sources": [{"id": 1, "url": "https://a.io", "title": "a", "content": "$5", "provider": "tavily"}],
        "tool_log": [],
        "checks": [],
        "revision": revision,
    }


def _run(monkeypatch, critique: Critique, revision: int = 0) -> dict:
    class Fake:
        def invoke(self, _messages):
            return critique

    monkeypatch.setattr(critic_mod, "get_llm", lambda *a, **k: Fake())
    state = _state(revision)
    out = critic_mod.critic(state)
    state.update(out)
    return state


@pytest.mark.parametrize(
    "verdict, route", [("accept", "end"), ("needs_research", "planner"), ("needs_rewrite", "writer")]
)
def test_routes_by_verdict(monkeypatch, verdict, route):
    state = _run(monkeypatch, Critique(score=8 if verdict == "accept" else 4, verdict=verdict))
    assert critic_mod.route_after_critic(state) == route
    assert state["revision"] == (0 if verdict == "accept" else 1)


def test_revision_cap_ends_with_reviewer_notes(monkeypatch):
    c = Critique(score=4, verdict="needs_rewrite", issues=["Units are wrong"])
    state = _run(monkeypatch, c, revision=config.MAX_REVISIONS)
    assert critic_mod.route_after_critic(state) == "end"
    assert state["revision"] == config.MAX_REVISIONS
    assert "## Reviewer notes (unresolved)" in state["draft"] and "Units are wrong" in state["draft"]


def test_guardrails_override_inconsistent_accept(monkeypatch):
    state = _run(monkeypatch, Critique(score=9, verdict="accept", constraint_violations=["official page never fetched"]))
    assert state["critique"]["verdict"] == "needs_research"
    state = _run(monkeypatch, Critique(score=5, verdict="accept"))
    assert state["critique"]["verdict"] == "needs_rewrite"
