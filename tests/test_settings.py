"""Tests for the runtime secrets overlay and the Settings API.

Key invariant under test: keys can be set from the UI, but their *values* are never
returned in a response and never stored in the database — only a local file and only
their presence is exposed.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from fastapi.testclient import TestClient

import jobfinder.secrets_store as ss
import jobfinder.web as web

_ENV_VARS = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "RAPIDAPI_KEY", "JSEARCH_API_KEY",
             "ADZUNA_APP_ID", "ADZUNA_APP_KEY", "JOOBLE_API_KEY", "CAREERJET_AFFID",
             "FREELANCER_TOKEN", "JOBFINDER_MODEL")


@pytest.fixture
def tmp_secrets(tmp_path, monkeypatch):
    """Point the secrets file at a temp path (never the real data dir) and clear env keys."""
    monkeypatch.setattr(ss, "_FILE", tmp_path / "secrets.json")
    for v in _ENV_VARS:
        monkeypatch.delenv(v, raising=False)
    ss.reset_cache()
    yield tmp_path / "secrets.json"
    ss.reset_cache()


# --- overlay --------------------------------------------------------------

def test_env_wins_over_file(tmp_secrets, monkeypatch):
    ss.set_many({"jooble_key": "from-file"})
    assert ss.get("jooble_key") == "from-file" and ss.is_env("jooble_key") is False
    monkeypatch.setenv("JOOBLE_API_KEY", "from-env")
    assert ss.get("jooble_key") == "from-env" and ss.is_env("jooble_key") is True


def test_file_persists_and_empty_clears(tmp_secrets):
    ss.set_many({"jooble_key": "abc"})
    assert json.loads(tmp_secrets.read_text())["jooble_key"] == "abc"
    ss.reset_cache()                       # force reload from disk
    assert ss.get("jooble_key") == "abc"
    ss.set_many({"jooble_key": ""})        # empty string clears
    assert ss.get("jooble_key") is None
    ss.set_many({"jooble_key": None})      # None leaves unchanged (still cleared)
    assert ss.get("jooble_key") is None


def test_model_default_and_present(tmp_secrets):
    assert ss.model()                      # falls back to the configured default
    assert ss.present() == {"jsearch": False, "adzuna": False, "jooble": False,
                            "careerjet": False, "freelancer": False, "findwork": False}
    ss.set_many({"adzuna_app_id": "id", "adzuna_app_key": "key"})
    assert ss.present()["adzuna"] is True


# --- Settings API ---------------------------------------------------------

def test_settings_set_key_never_returns_the_value(tmp_secrets):
    client = TestClient(web.app)
    assert client.get("/api/settings").json()["present"]["jooble"] is False
    r = client.post("/api/settings", json={"jooble_key": "SECRET-XYZ", "model": "claude-haiku-4-5"})
    assert r.status_code == 200
    d = r.json()
    assert d["present"]["jooble"] is True and d["model"] == "claude-haiku-4-5"
    assert "SECRET-XYZ" not in r.text                                   # POST response
    assert "SECRET-XYZ" not in client.get("/api/settings").text         # subsequent GET
    assert "SECRET-XYZ" in tmp_secrets.read_text()                      # but it IS persisted to the file


def test_settings_rejects_unknown_model(tmp_secrets):
    assert TestClient(web.app).post("/api/settings", json={"model": "gpt-4"}).status_code == 422


def test_settings_marks_env_locked(tmp_secrets, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "env-key")
    d = TestClient(web.app).get("/api/settings").json()
    assert d["env_locked"]["anthropic_key"] is True
    assert d["present"]["anthropic"] is True
