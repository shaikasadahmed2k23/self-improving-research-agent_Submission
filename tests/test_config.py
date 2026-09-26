import importlib

import pytest

from agent import config


@pytest.fixture
def reload_config(monkeypatch):
    def _reload(**env):
        for key in ("TOKEN_SAVER", "MAX_PLAN_STEPS", "PAGE_CHAR_LIMIT", "STEP_CONTEXT_CHARS"):
            monkeypatch.delenv(key, raising=False)
        for key, value in env.items():
            monkeypatch.setenv(key, value)
        monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **k: None)  # isolate from the real .env
        return importlib.reload(config)

    yield _reload
    monkeypatch.undo()
    importlib.reload(config)


def test_token_saver_caps_limits(reload_config):
    cfg = reload_config(TOKEN_SAVER="true", MAX_PLAN_STEPS="6", PAGE_CHAR_LIMIT="800")
    assert cfg.MAX_PLAN_STEPS == 3  # .env value above the cap is lowered
    assert cfg.PAGE_CHAR_LIMIT == 800  # smaller explicit value wins
    assert cfg.STEP_CONTEXT_CHARS == 600  # "no limit" default gets the cap


def test_limits_unchanged_without_token_saver(reload_config):
    cfg = reload_config(MAX_PLAN_STEPS="6")
    assert (cfg.MAX_PLAN_STEPS, cfg.PAGE_CHAR_LIMIT, cfg.STEP_CONTEXT_CHARS) == (6, 3000, 0)


def test_json_mode_structured_retries_once_on_invalid_json():
    from langchain_core.language_models import FakeListChatModel

    from agent.llm import json_mode_structured
    from agent.state import Plan

    llm = FakeListChatModel(responses=['{"steps": "oops"}', '```json\n{"steps": [{"goal": "g", "search_query": "q"}]}\n```'])
    plan = json_mode_structured(llm, Plan).invoke([("system", "Plan."), ("human", "task")])
    assert plan.steps[0].goal == "g"
