"""API-level tests for the draft/outbox endpoints (no network, template generator)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from fastapi.testclient import TestClient

from jobfinder.web import app

client = TestClient(app)
SAMPLE = (Path(__file__).parent / "sample_cv.txt").read_text(encoding="utf-8")

JOB = {
    "title": "Backend Engineer", "company": "Globex", "url": "https://example.com/j",
    "source": "LinkedIn", "score": 70, "description": "Python, Django, AWS.",
    "matched_skills": ["python", "django", "aws"], "missing_skills": ["rust"],
}


def _upload_cv() -> str:
    r = client.post("/api/upload-text", data={"text": SAMPLE})
    assert r.status_code == 200
    return r.json()["cv_id"]


def test_draft_config():
    d = client.get("/api/draft-config").json()
    assert "llm_available" in d and "model" in d


def test_generate_list_update_delete_draft():
    cv_id = _upload_cv()
    # generate (force template so the test never needs a key/network)
    r = client.post("/api/drafts/generate", json={"cv_id": cv_id, "jobs": [JOB], "use_llm": False})
    assert r.status_code == 200
    drafts = r.json()["drafts"]
    assert len(drafts) == 1
    did = drafts[0]["id"]
    assert drafts[0]["generator"] == "template"
    assert "Backend Engineer" in drafts[0]["subject"]
    assert "Jane Doe" in drafts[0]["body"]

    # appears in the outbox list
    assert any(d["id"] == did for d in client.get("/api/drafts").json()["drafts"])

    # edit + mark ready
    r = client.put(f"/api/drafts/{did}", json={"body": "Edited body.", "status": "ready"})
    assert r.status_code == 200 and r.json()["status"] == "ready" and r.json()["body"] == "Edited body."

    # export
    r = client.get(f"/api/drafts/{did}/export")
    assert r.status_code == 200 and "Edited body." in r.text
    assert "attachment" in r.headers.get("content-disposition", "")

    # delete
    assert client.delete(f"/api/drafts/{did}").status_code == 200
    assert all(d["id"] != did for d in client.get("/api/drafts").json()["drafts"])


def test_generate_requires_known_cv():
    r = client.post("/api/drafts/generate", json={"cv_id": "nope", "jobs": [JOB]})
    assert r.status_code == 404


def test_generate_rejects_empty_jobs():
    cv_id = _upload_cv()
    r = client.post("/api/drafts/generate", json={"cv_id": cv_id, "jobs": []})
    assert r.status_code == 400


def test_examples_add_list_delete():
    r = client.post("/api/examples-text", data={"text": "My example letter.", "name": "ex1"})
    assert r.status_code == 200
    eid = r.json()["id"]
    assert any(e["id"] == eid for e in client.get("/api/examples").json()["examples"])
    assert client.delete(f"/api/examples/{eid}").status_code == 200
    assert all(e["id"] != eid for e in client.get("/api/examples").json()["examples"])
