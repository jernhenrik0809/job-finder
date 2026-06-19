"""API-level tests for the consulting engine endpoints — the bench (consultants), the
single-row house, and gig->bench ranking. No network: every path here is pure/local.

State note: the suite runs against a process-global in-memory store (``web.store``, forced by
conftest), so rows created here persist across tests in this module/run. Each test therefore
seeds its OWN data and asserts on what it created (by id), never on absolute table counts —
mirroring ``tests/test_web.py``, which does the same against the shared client.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from jobfinder.web import app

client = TestClient(app)

CV_TEXT = "Jane Doe\nSenior Python Engineer\nSkills: Python, Django, AWS."


# --- helpers --------------------------------------------------------------

def _upload_text(text: str = CV_TEXT) -> str:
    r = client.post("/api/upload-text", data={"text": text})
    assert r.status_code == 200
    return r.json()["cv_id"]


def _create(**body) -> dict:
    r = client.post("/api/consultants", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def _delete(cid: str) -> None:
    client.delete(f"/api/consultants/{cid}")


# --- POST /api/consultants ------------------------------------------------

def test_create_consultant_from_pasted_text_parses_skills_and_gets_id():
    c = _create(text="Programmer\nSkills: Python, Django, AWS.")
    assert c["id"]                                   # a generated id
    assert c["cv_id"]                                # text path stores a profile + links it
    assert "python" in c["skills"]                   # parsed + lower-cased
    assert {"django", "aws"} <= set(c["skills"])
    assert c["raw_text"]                             # CV text carried for matching
    _delete(c["id"])


def test_create_consultant_from_existing_cv_id_carries_skills():
    cv_id = _upload_text()
    c = _create(cv_id=cv_id)
    assert c["cv_id"] == cv_id
    assert "python" in c["skills"]                   # skills carried over from the uploaded profile
    _delete(c["id"])


def test_create_consultant_from_unknown_cv_id_is_404():
    assert client.post("/api/consultants", json={"cv_id": "no-such-cv"}).status_code == 404


def test_create_consultant_explicit_overrides_persist():
    c = _create(
        name="Override Person", text=CV_TEXT,
        sell_rate=1200, currency="DKK", engagement_type="subcontractor",
        right_to_present=False,
    )
    assert c["name"] == "Override Person"
    assert c["sell_rate"] == 1200.0
    assert c["currency"] == "DKK"
    assert c["engagement_type"] == "subcontractor"
    assert c["right_to_present"] is False
    # round-trips through the store, not just the response object
    got = client.get(f"/api/consultants/{c['id']}").json()
    assert got["engagement_type"] == "subcontractor" and got["sell_rate"] == 1200.0
    _delete(c["id"])


def test_create_consultant_does_not_accept_status_at_create():
    # CONTRACT: ``status`` is a PATCH-only field (ConsultantCreate has no ``status``), so a
    # ``status`` in the create body is ignored and the new bench member onboards "active".
    # Deactivation is an explicit later step via PATCH (see test_patch_consultant_persists_changes).
    c = _create(name="Should Be Active", text=CV_TEXT, status="inactive")
    assert c["status"] == "active"                   # create defaults active; status not set here
    _delete(c["id"])


def test_create_consultant_invalid_engagement_type_falls_back_to_default():
    # An unknown enum value is IGNORED (not stored verbatim) -> the dataclass default "associate".
    c = _create(name="Bad Enum", engagement_type="contractor-of-doom")
    assert c["engagement_type"] == "associate"
    assert c["engagement_type"] != "contractor-of-doom"
    _delete(c["id"])


# --- GET /api/consultants -------------------------------------------------

def test_list_consultants_includes_created_and_enum_catalogs():
    c = _create(name="Listed One", text=CV_TEXT)
    body = client.get("/api/consultants").json()
    ids = {x["id"] for x in body["consultants"]}
    assert c["id"] in ids                            # the one we created shows up
    # the three enum catalogs the UI needs to render dropdowns
    assert "associate" in body["engagement_types"]
    assert "direct_from_subject" in body["data_origins"]
    assert set(body["statuses"]) == {"active", "inactive"}
    _delete(c["id"])


# --- GET /api/consultants/{id} --------------------------------------------

def test_get_consultant_real_and_missing():
    c = _create(name="Fetch Me", text=CV_TEXT)
    got = client.get(f"/api/consultants/{c['id']}")
    assert got.status_code == 200 and got.json()["id"] == c["id"]
    assert client.get("/api/consultants/does-not-exist").status_code == 404
    _delete(c["id"])


# --- PATCH /api/consultants/{id} ------------------------------------------

def test_patch_consultant_persists_changes():
    c = _create(name="Patch Me", text=CV_TEXT, sell_rate=900)
    r = client.patch(f"/api/consultants/{c['id']}", json={
        "status": "inactive", "sell_rate": 1500, "available_from": "2026-09-01",
    })
    assert r.status_code == 200
    upd = r.json()
    assert upd["status"] == "inactive"
    assert upd["sell_rate"] == 1500.0
    assert upd["available_from"] == "2026-09-01"
    # persisted (re-read from the store)
    got = client.get(f"/api/consultants/{c['id']}").json()
    assert got["status"] == "inactive" and got["sell_rate"] == 1500.0
    _delete(c["id"])


def test_patch_consultant_missing_is_404():
    assert client.patch("/api/consultants/nope", json={"status": "inactive"}).status_code == 404


# --- DELETE /api/consultants/{id} -----------------------------------------

def test_delete_consultant_removes_it():
    c = _create(name="Delete Me", text=CV_TEXT)
    r = client.delete(f"/api/consultants/{c['id']}")
    assert r.status_code == 200 and r.json() == {"ok": True}
    assert client.get(f"/api/consultants/{c['id']}").status_code == 404


# --- GET/POST /api/house --------------------------------------------------

def test_house_get_default_is_ok():
    # Empty/default house never errors (single-row, returns a blank House when unset).
    r = client.get("/api/house")
    assert r.status_code == 200
    assert r.json()["id"] == "house"                 # fixed single-row id


def test_house_post_persists_and_reflects():
    r = client.post("/api/house", json={"name": "Northwind Consulting", "voice": "warm, direct"})
    assert r.status_code == 200
    saved = r.json()
    assert saved["id"] == "house"                    # always the fixed single-row id
    assert saved["name"] == "Northwind Consulting"
    assert saved["voice"] == "warm, direct"
    # GET reflects the saved identity
    got = client.get("/api/house").json()
    assert got["name"] == "Northwind Consulting" and got["voice"] == "warm, direct"
    assert got["id"] == "house"


# --- POST /api/bench/rank -------------------------------------------------

def _seed_three_bench_members():
    """A strong match, a weak/no-skill match, and an inactive (but otherwise strong) one.
    Returns their ids so the test can isolate them from any other rows in the shared store."""
    strong = _create(
        name="Strong Match",
        text="Senior Python Engineer. Django REST APIs deployed on AWS for 8 years.",
        skills=["python", "django", "aws"], title="Python Engineer",
    )
    weak = _create(
        name="Weak Match",
        text="Java and Spring Boot developer, mostly enterprise backend.",
        skills=["java"], title="Java Developer",
    )
    inactive = _create(
        name="Inactive Strong",
        text="Python Django AWS expert with a decade of delivery.",
        skills=["python", "django", "aws"], title="Python Engineer",
    )
    # status is PATCH-only (not settable at create) -> deactivate explicitly.
    r = client.patch(f"/api/consultants/{inactive['id']}", json={"status": "inactive"})
    assert r.status_code == 200 and r.json()["status"] == "inactive"
    inactive = r.json()
    return strong, weak, inactive


def test_bench_rank_orders_strong_first_and_hard_gates_inactive():
    strong, weak, inactive = _seed_three_bench_members()
    try:
        r = client.post("/api/bench/rank", json={
            "title": "Senior Python Engineer",
            "description": "Build Django APIs on AWS.",
            "skills": ["python", "django", "aws"],
        })
        assert r.status_code == 200
        data = r.json()
        assert "matches" in data and isinstance(data["matches"], list)
        assert data["bench_size"] >= 3               # at least our three seeded members

        by_id = {m["consultant"]["id"]: m for m in data["matches"]}
        ms, mw, mi = by_id[strong["id"]], by_id[weak["id"]], by_id[inactive["id"]]

        # strong: eligible, real score, ranked above the weak one
        assert ms["eligible"] is True and ms["score"] > 0
        order = [m["consultant"]["id"] for m in data["matches"]]
        assert order.index(strong["id"]) < order.index(weak["id"])

        # inactive: HARD-gated -> not eligible, score 0, explicit disqualifier
        assert mi["eligible"] is False
        assert mi["score"] == 0
        assert mi["disqualifiers"] and isinstance(mi["disqualifiers"], list)

        # ineligible sorts below ALL eligible ones (the inactive one is last among our trio)
        assert order.index(inactive["id"]) > order.index(strong["id"])
        assert order.index(inactive["id"]) > order.index(weak["id"])
    finally:
        for c in (strong, weak, inactive):
            _delete(c["id"])


def test_bench_rank_matched_skills_reflect_coverage():
    strong, weak, inactive = _seed_three_bench_members()
    try:
        r = client.post("/api/bench/rank", json={
            "title": "Python Engineer", "skills": ["python", "django", "aws"],
        })
        data = r.json()
        by_id = {m["consultant"]["id"]: m for m in data["matches"]}
        ms, mw = by_id[strong["id"]], by_id[weak["id"]]
        # the strong consultant covers all three project skills; the weak one covers none
        assert {s.lower() for s in ms["matched_skills"]} == {"python", "django", "aws"}
        assert ms["missing_skills"] == []
        assert mw["matched_skills"] == []
        assert {s.lower() for s in mw["missing_skills"]} == {"python", "django", "aws"}
    finally:
        for c in (strong, weak, inactive):
            _delete(c["id"])


def test_bench_rank_requires_a_project_description():
    # Neither title nor description/text -> 400.
    assert client.post("/api/bench/rank", json={"skills": ["python"]}).status_code == 400
    assert client.post("/api/bench/rank", json={}).status_code == 400


def test_bench_rank_accepts_a_job_card():
    strong, weak, inactive = _seed_three_bench_members()
    try:
        r = client.post("/api/bench/rank", json={
            "job": {
                "title": "Senior Python Engineer",
                "job_skills": ["python", "django", "aws"],
                "location": "Copenhagen",
            }
        })
        assert r.status_code == 200
        data = r.json()
        assert data["project"]["title"] == "Senior Python Engineer"
        assert data["project"]["location"] == "Copenhagen"
        by_id = {m["consultant"]["id"]: m for m in data["matches"]}
        # job_skills drive the same coverage as explicit skills did
        assert {s.lower() for s in by_id[strong["id"]]["matched_skills"]} == {"python", "django", "aws"}
    finally:
        for c in (strong, weak, inactive):
            _delete(c["id"])


def test_bench_rank_tolerates_null_string_fields():
    """The UI sends null for empty inputs (location/currency/start_date/...); the endpoint must
    accept null for its string fields (coerced to "") rather than 422. Regression for the
    integration bug where typed-str fields rejected the UI's null payload."""
    r = client.post("/api/bench/rank", json={
        "title": "Python Engineer", "description": None, "text": None,
        "skills": ["python"], "location": None, "currency": None,
        "start_date": None, "end_date": None, "required_clearance": None,
    })
    assert r.status_code == 200, r.text
    assert "matches" in r.json() and "bench_size" in r.json()


def test_created_consultant_is_presentable_and_eligible_by_default():
    """A consultant onboarded without an explicit right_to_present must default to presentable
    (not silently excluded). Guards the create path against a 'not cleared to present' regression."""
    c = _create(text=CV_TEXT, skills=["python", "django", "aws"])
    try:
        assert c["right_to_present"] is True
        r = client.post("/api/bench/rank", json={"title": "Python Engineer", "skills": ["python"]})
        assert r.status_code == 200
        mine = [m for m in r.json()["matches"] if m["consultant"]["id"] == c["id"]]
        assert mine and mine[0]["eligible"] is True and mine[0]["score"] > 0
    finally:
        _delete(c["id"])
