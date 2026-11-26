import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import research  # noqa: E402


def write_lock(tmp_path, resources):
    lock = tmp_path / "claude-lock.json"
    lock.write_text(json.dumps({"resources": resources}))
    return lock


def test_load_ids_from_lock_file(tmp_path):
    lock = write_lock(tmp_path, {
        "./agents/deep-researcher/agent.md": {"id": "agent_123"},
        "./agents/deep-researcher/environment.yaml": {"id": "env_456"},
    })
    assert research.load_ids(lock, env={}) == ("agent_123", "env_456")


def test_load_ids_accepts_paths_without_dot_prefix(tmp_path):
    lock = write_lock(tmp_path, {
        "agents/deep-researcher/agent.md": {"id": "agent_123"},
        "agents/deep-researcher/environment.yaml": {"id": "env_456"},
    })
    assert research.load_ids(lock, env={}) == ("agent_123", "env_456")


def test_env_vars_override_lock_file(tmp_path):
    lock = write_lock(tmp_path, {
        "./agents/deep-researcher/agent.md": {"id": "agent_123"},
        "./agents/deep-researcher/environment.yaml": {"id": "env_456"},
    })
    ids = research.load_ids(lock, env={"AGENT_ID": "agent_env", "ENVIRONMENT_ID": "env_env"})
    assert ids == ("agent_env", "env_env")


def test_missing_ids_raise_helpful_error(tmp_path):
    with pytest.raises(research.ConfigError, match="ant apply"):
        research.load_ids(tmp_path / "missing.json", env={})


def test_outcome_event_shape():
    event = research.build_outcome("Was ist X?", max_iterations=5)
    assert event["type"] == "user.define_outcome"
    assert "Was ist X?" in event["description"]
    assert event["rubric"] == {"type": "text", "content": research.RUBRIC}
    assert event["max_iterations"] == 5


def test_approve_denies_when_unattended(monkeypatch):
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    assert research.approve(object()) is False
