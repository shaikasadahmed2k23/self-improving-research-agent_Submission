"""Daily live-run cap for the public demo."""
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from agent import config, usage

APP = str(Path(__file__).resolve().parent.parent / "app.py")


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "MEMORY_DB_PATH", tmp_path / "agent_memory.db")
    return tmp_path


def test_claims_stop_at_the_cap_and_reset_the_next_day(data_dir, monkeypatch):
    assert [usage.claim_run(cap=2) for _ in range(3)] == [(True, 1), (True, 2), (False, 2)]
    assert usage.runs_today() == 2
    monkeypatch.setattr(usage, "_today", lambda: "2099-01-01")
    assert usage.claim_run(cap=2) == (True, 1)


def test_cap_zero_means_no_limit(data_dir):
    assert all(usage.claim_run(cap=0)[0] for _ in range(20))


def test_counts_are_not_listed_as_a_memory_database(data_dir):
    usage.claim_run(cap=5)
    assert not list(data_dir.glob("*.db")) or all(p.name != "usage.sqlite3" for p in data_dir.glob("*.db"))
    assert (data_dir / "usage.sqlite3").exists()


def _live_app(task="What does Pinecone cost?"):
    at = AppTest.from_file(APP, default_timeout=30).run()
    at.text_area[0].set_value(task).run()
    return at


def test_ui_blocks_live_runs_at_the_cap_and_points_to_replay(data_dir, monkeypatch):
    monkeypatch.setattr(config, "DAILY_RUN_CAP", 2)
    calls = []
    monkeypatch.setattr("agent.runner.stream_run", lambda *a, **k: calls.append(a) or iter([("done", {"tokens": {}})]))
    usage.claim_run(cap=2)
    usage.claim_run(cap=2)

    at = _live_app()
    assert not at.exception
    assert any("Live runs today: 2/2" in c.value for c in at.caption)
    info = " ".join(i.value for i in at.info)
    assert "live-run limit (2)" in info and "Replay a recorded run" in info
    assert at.button[0].disabled
    assert calls == []


def test_ui_counts_each_live_run(data_dir, monkeypatch):
    monkeypatch.setattr(config, "DAILY_RUN_CAP", 5)
    monkeypatch.setattr("agent.runner.stream_run", lambda *a, **k: iter([("done", {"tokens": {}})]))
    at = _live_app()
    at.button[0].click().run()
    assert not at.exception
    assert usage.runs_today() == 1


def test_ui_rechecks_the_cap_when_the_button_is_clicked(data_dir, monkeypatch):
    """Another visitor may take the last run between page render and click."""
    monkeypatch.setattr(config, "DAILY_RUN_CAP", 1)
    calls = []
    monkeypatch.setattr("agent.runner.stream_run", lambda *a, **k: calls.append(a) or iter([("done", {"tokens": {}})]))
    at = _live_app()
    usage.claim_run(cap=1)  # someone else, after this visitor's page rendered
    at.button[0].click().run()
    assert calls == []
    assert any("live-run limit (1)" in i.value for i in at.info)
