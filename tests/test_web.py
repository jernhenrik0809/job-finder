"""API-level tests for the application/pipeline endpoints (no network, template generator)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from jobfinder.web import app

client = TestClient(app)
SAMPLE = (Path(__file__).parent / "sample_cv.txt").read_text(encoding="utf-8")

JOB = {
    "title": "Backend Engineer", "company": "Globex", "url": "https://example.com/j",
    "source": "LinkedIn", "score": 70, "location": "Remote", "description": "Python, Django, AWS.",
    "matched_skills": ["python", "django", "aws"], "missing_skills": ["rust"],
}


def _upload_cv() -> str:
    r = client.post("/api/upload-text", data={"text": SAMPLE})
    assert r.status_code == 200
    return r.json()["cv_id"]


def test_draft_config_exposes_statuses():
    d = client.get("/api/draft-config").json()
    assert "llm_available" in d and "model" in d
    assert "saved" in d["statuses"] and "offer" in d["statuses"]


def test_generate_creates_trackable_applications():
    cv_id = _upload_cv()
    r = client.post("/api/applications/generate", json={"cv_id": cv_id, "jobs": [JOB], "use_llm": False})
    assert r.status_code == 200
    apps = r.json()["applications"]
    assert len(apps) == 1
    a = apps[0]; aid = a["id"]
    assert a["generator"] == "template" and a["status"] == "ready"
    assert "Backend Engineer" in a["subject"] and "Jane Doe" in a["body"]
    assert a["cv_id"] == cv_id and a["job"]["matched_skills"] == ["python", "django", "aws"]

    # appears in the pipeline list
    assert any(x["id"] == aid for x in client.get("/api/applications").json()["applications"])

    # lifecycle transition is validated, logs an event, stamps applied_at
    r = client.patch(f"/api/applications/{aid}", json={"status": "applied", "notes": "called recruiter"})
    assert r.status_code == 200
    a2 = r.json()
    assert a2["status"] == "applied" and a2["applied_at"] and a2["notes"] == "called recruiter"
    assert any(e["type"] == "status" for e in a2["events"])

    # an unknown status is rejected
    assert client.patch(f"/api/applications/{aid}", json={"status": "promoted"}).status_code == 400

    # regenerate reuses the stored cv_id + job snapshot (no cv_id in the request body)
    r = client.post(f"/api/applications/{aid}/regenerate", json={"use_llm": False})
    assert r.status_code == 200 and "Backend Engineer" in r.json()["subject"]

    # export + delete
    r = client.get(f"/api/applications/{aid}/export")
    assert r.status_code == 200 and "Jane Doe" in r.text and "attachment" in r.headers.get("content-disposition", "")
    assert client.delete(f"/api/applications/{aid}").status_code == 200
    assert all(x["id"] != aid for x in client.get("/api/applications").json()["applications"])


def test_tailor_endpoint():
    cv_id = _upload_cv()
    aid = client.post("/api/applications/generate", json={"cv_id": cv_id, "jobs": [JOB], "use_llm": False}).json()["applications"][0]["id"]
    r = client.post(f"/api/applications/{aid}/tailor", json={"use_llm": False})
    assert r.status_code == 200
    data = r.json()
    assert {"emphasize_skills", "bullets", "gaps"} <= set(data)
    assert all("text" in b and "source_index" in b for b in data["bullets"])   # provenance
    client.delete(f"/api/applications/{aid}")


def test_save_to_pipeline_without_a_letter():
    cv_id = _upload_cv()
    r = client.post("/api/applications", json={"cv_id": cv_id, "job": JOB})
    assert r.status_code == 200
    a = r.json()
    assert a["status"] == "saved" and a["body"] == "" and a["generator"] == ""
    client.delete(f"/api/applications/{a['id']}")


def test_generate_requires_known_cv():
    assert client.post("/api/applications/generate", json={"cv_id": "nope", "jobs": [JOB]}).status_code == 404


def test_generate_rejects_empty_jobs():
    cv_id = _upload_cv()
    assert client.post("/api/applications/generate", json={"cv_id": cv_id, "jobs": []}).status_code == 400


def test_insights_endpoint():
    cv_id = _upload_cv()
    aid = client.post("/api/applications/generate", json={"cv_id": cv_id, "jobs": [JOB], "use_llm": False}).json()["applications"][0]["id"]
    client.patch(f"/api/applications/{aid}", json={"status": "applied"})
    ins = client.get("/api/insights").json()
    assert {"funnel", "response_rate", "nudges", "by_source", "over_time"} <= set(ins)
    assert {f["stage"] for f in ins["funnel"]} == {"saved", "drafted", "applied", "interviewing", "offer"}
    assert ins["total"] >= 1
    client.delete(f"/api/applications/{aid}")


def test_saved_search_create_run_seen_delete(monkeypatch):
    cv_id = _upload_cv()
    r = client.post("/api/saved-searches", json={"name": "Py", "cv_id": cv_id, "keywords": "python", "sources": ["remotive"]})
    assert r.status_code == 200
    sid = r.json()["id"]
    assert any(x["id"] == sid for x in client.get("/api/saved-searches").json()["searches"])

    # mock the live search so the test is hermetic
    import jobfinder.web as web
    from jobfinder.engine import SearchResult
    from jobfinder.sources.base import Job
    jobs = [Job(title="Python Dev", company="Acme", source="Remotive"),
            Job(title="Backend Engineer", company="Globex", source="Remotive")]
    for j in jobs:
        j.score = 50
    monkeypatch.setattr(web, "find_jobs", lambda profile, settings: SearchResult(jobs=jobs, profile=profile))

    run = client.post(f"/api/saved-searches/{sid}/run").json()
    assert len(run["jobs"]) == 2 and len(run["new_ids"]) == 2 and run["new_count"] == 2

    run2 = client.post(f"/api/saved-searches/{sid}/run").json()    # same jobs → nothing new
    assert run2["new_ids"] == [] and run2["new_count"] == 2

    assert client.post(f"/api/saved-searches/{sid}/seen").json()["new_count"] == 0
    assert client.delete(f"/api/saved-searches/{sid}").status_code == 200
    assert all(x["id"] != sid for x in client.get("/api/saved-searches").json()["searches"])


def test_examples_add_list_delete():
    r = client.post("/api/examples-text", data={"text": "My example letter.", "name": "ex1"})
    assert r.status_code == 200
    eid = r.json()["id"]
    assert any(e["id"] == eid for e in client.get("/api/examples").json()["examples"])
    assert client.delete(f"/api/examples/{eid}").status_code == 200
    assert all(e["id"] != eid for e in client.get("/api/examples").json()["examples"])


def test_profile_update_applies_corrections_and_persists():
    cv_id = _upload_cv()
    r = client.patch(f"/api/profile/{cv_id}", json={
        "skills": ["Python", "  django ", "django", ""],    # dedupe + strip + drop blanks
        "titles": ["Backend Engineer"],
        "location": "Copenhagen",
        "seniority": "Senior",
        "years_experience": 9,
    })
    assert r.status_code == 200
    p = r.json()["profile"]
    assert p["skills"] == ["python", "django"]              # lowercased, deduped
    assert p["titles"] == ["Backend Engineer"]
    assert p["location"] == "Copenhagen" and p["seniority"] == "senior"
    assert p["years_experience"] == 9

    # persisted in the store, and the corrected skills are what the matcher will use
    import jobfinder.web as web
    stored = web.store.get_profile(cv_id)
    assert stored.skills == ["python", "django"] and stored.titles == ["Backend Engineer"]


def test_profile_update_partial_leaves_other_fields():
    cv_id = _upload_cv()
    before = client.patch(f"/api/profile/{cv_id}", json={"location": "Aarhus"}).json()["profile"]
    # titles/skills from the parsed CV are untouched by a location-only edit
    after = client.patch(f"/api/profile/{cv_id}", json={"seniority": "lead"}).json()["profile"]
    assert after["location"] == "Aarhus"                    # earlier edit retained
    assert after["seniority"] == "lead"


def test_profile_update_clamps_years_and_rejects_unknown_cv():
    cv_id = _upload_cv()
    p = client.patch(f"/api/profile/{cv_id}", json={"years_experience": 999}).json()["profile"]
    assert p["years_experience"] == 80                       # clamped
    assert client.patch("/api/profile/does-not-exist", json={"location": "x"}).status_code == 404


def test_profile_update_refreshes_suggested_keywords():
    # correcting the title must also drive the default search query (regression):
    # an empty keyword box should search the corrected role, not the parsed guess.
    cv_id = _upload_cv()
    p = client.patch(f"/api/profile/{cv_id}", json={"titles": ["Machine Learning Engineer"]}).json()["profile"]
    assert p["suggested_keywords"] == "Machine Learning Engineer"
    # falls back to the top skill when there is no title
    p2 = client.patch(f"/api/profile/{cv_id}", json={"titles": [], "skills": ["Kubernetes"]}).json()["profile"]
    assert p2["suggested_keywords"] == "kubernetes"
