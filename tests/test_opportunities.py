"""Tests for the OPPORTUNITY path — the durable bid record + its append-only audit trail.

Three groups, mirroring tests/test_proposals.py and tests/test_bench_web.py:
  (A) UNIT   — ``jobfinder.opportunities`` functions, imported directly (no server, no network).
  (B) STORE  — round-trip / lookup / atomic update against BOTH SqliteStore and MemoryStore.
  (C) ENDPOINT — drive the FastAPI app via TestClient, exactly like tests/test_bench_web.py.

State note (mirrors test_bench_web.py): the endpoint suite runs against a process-global
in-memory store (forced by conftest), so rows created here persist across tests in this run.
Each endpoint test seeds its OWN data and asserts on what it created (by id), never on absolute
table counts, cleaning up afterwards.

Everything here is deterministic and offline: with no ANTHROPIC_API_KEY configured the proposal
path falls back to the grounded offline template, so ``blocking`` is False and ``used_llm`` False.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from fastapi.testclient import TestClient

from jobfinder.opportunities import (
    Opportunity, STATUSES,
    new_opportunity, record_event, set_status, set_staffing, attach_proposal, margin_of,
)
from jobfinder.store.sqlite import SqliteStore
from jobfinder.store.memory import MemoryStore
from jobfinder.web import app

client = TestClient(app)


# ===========================================================================
# (A) UNIT — jobfinder.opportunities
# ===========================================================================

def _event_types(opp):
    return [e["type"] for e in opp.events]


def test_new_opportunity_sets_fields_and_initial_created_event():
    opp = new_opportunity({
        "title": "Senior Python Engineer", "source": "Verama", "source_uid": "V-1",
        "description": "Build Django APIs.", "skills": ["python", "django"],
        "location": "Copenhagen", "currency": "DKK", "rate_ceiling": 1100,
    })
    assert opp.title == "Senior Python Engineer"
    assert opp.source == "Verama" and opp.source_uid == "V-1"
    assert opp.skills == ["python", "django"]
    assert opp.location == "Copenhagen" and opp.currency == "DKK"
    assert opp.rate_ceiling == 1100.0
    assert opp.status == "lead"               # default starting status
    assert opp.created > 0 and opp.updated > 0
    # exactly one initial "created" event, carrying the idempotency key in meta
    assert _event_types(opp) == ["created"]
    ev = opp.events[0]
    assert ev["meta"]["source"] == "Verama" and ev["meta"]["source_uid"] == "V-1"


def test_new_opportunity_defaults_title_and_drops_non_string_skills():
    opp = new_opportunity({"skills": ["python", 123, None, "aws"]})
    assert opp.title == "Untitled project"
    assert opp.skills == ["python", "aws"]    # non-string entries dropped


def test_record_event_is_append_only_and_bumps_updated():
    opp = new_opportunity({"title": "Gig"})
    assert len(opp.events) == 1               # the "created" event
    first = opp.events[0]
    before = opp.updated
    record_event(opp, "note", "a second event", {"k": "v"})
    # the first event is preserved (append-only), the new one is added after it
    assert len(opp.events) == 2
    assert opp.events[0] is first             # untouched
    assert opp.events[1]["type"] == "note" and opp.events[1]["meta"] == {"k": "v"}
    assert opp.updated >= before              # updated bumped


def test_set_status_validates_logs_and_no_ops_when_unchanged():
    opp = new_opportunity({"title": "Gig"})
    # unknown status -> ValueError, nothing logged
    with pytest.raises(ValueError):
        set_status(opp, "definitely-not-a-status")
    assert _event_types(opp) == ["created"]

    # a real transition logs a "status" event
    set_status(opp, "qualifying")
    assert opp.status == "qualifying"
    assert _event_types(opp) == ["created", "status"]

    # setting the SAME status again is a no-op (no duplicate event)
    set_status(opp, "qualifying")
    assert _event_types(opp) == ["created", "status"]


def test_set_staffing_builds_clean_lines_and_drops_entries_without_consultant_id():
    opp = new_opportunity({"title": "Gig"})
    set_staffing(opp, [
        {"consultant_id": "c1", "consultant_name": "Anna", "cost_rate": 600, "sell_rate": 950, "currency": "DKK"},
        {"consultant_name": "No Id Here"},          # dropped: no consultant_id
        "not-a-dict",                                # dropped: not a dict
        {"consultant_id": "c2", "consultant_name": "Bo"},
    ])
    assert [l["consultant_id"] for l in opp.staffed] == ["c1", "c2"]
    ln = opp.staffed[0]
    assert ln["consultant_name"] == "Anna" and ln["cost_rate"] == 600.0 and ln["sell_rate"] == 950.0
    assert ln["currency"] == "DKK"
    # c2 has no rates -> coerced to None (clean line, not missing keys)
    assert opp.staffed[1]["cost_rate"] is None and opp.staffed[1]["sell_rate"] is None
    # a "staffed" event was logged, naming who is on the bid
    assert _event_types(opp) == ["created", "staffed"]
    assert opp.events[-1]["meta"]["consultant_ids"] == ["c1", "c2"]


def test_attach_proposal_advances_to_ready_when_not_blocking():
    opp = new_opportunity({"title": "Gig"})           # status "lead"
    qa = []
    attach_proposal(opp, "Subject line", "Body text", "template", qa, blocking=False)
    assert opp.proposal_subject == "Subject line"
    assert opp.proposal_body == "Body text"
    assert opp.proposal_generator == "template"
    assert opp.qa == []
    assert opp.status == "proposal_ready"             # advanced because not blocking
    assert _event_types(opp) == ["created", "proposal_generated"]
    meta = opp.events[-1]["meta"]
    assert meta["generator"] == "template" and meta["blocking"] is False


def test_attach_proposal_stays_drafting_when_blocking():
    opp = new_opportunity({"title": "Gig"})
    qa = [{"type": "unsupported_capability", "blocking": True}]
    attach_proposal(opp, "S", "B", "template", qa, blocking=True)
    assert opp.status == "proposal_drafting"          # held back because the QA gate blocks
    assert opp.qa == qa
    meta = opp.events[-1]["meta"]
    assert meta["blocking"] is True
    assert "unsupported_capability" in meta["qa_types"]


def test_margin_of_is_within_one_currency_and_none_when_a_rate_missing():
    assert margin_of({"cost_rate": 600, "sell_rate": 950, "currency": "DKK"}) == 350.0
    # a missing or unparseable rate yields None (never a wrong cross-FX number)
    assert margin_of({"cost_rate": 600, "currency": "DKK"}) is None
    assert margin_of({"sell_rate": 950}) is None
    assert margin_of({"cost_rate": "n/a", "sell_rate": 950}) is None


# ===========================================================================
# (B) STORE — SqliteStore + MemoryStore (parametrized over both backends)
# ===========================================================================

def _make_store(kind, tmp_path):
    return SqliteStore(tmp_path / "opps.db") if kind == "sqlite" else MemoryStore()


@pytest.mark.parametrize("kind", ["sqlite", "memory"])
def test_opportunity_round_trip_save_get_list_delete(kind, tmp_path):
    s = _make_store(kind, tmp_path)
    try:
        opp = new_opportunity({"title": "Gig", "source": "Verama", "source_uid": "V-1"})
        s.save_opportunity(opp)
        got = s.get_opportunity(opp.id)
        assert got is not None and got.id == opp.id and got.title == "Gig"
        assert [o.id for o in s.list_opportunities()] == [opp.id]
        s.delete_opportunity(opp.id)
        assert s.get_opportunity(opp.id) is None
        assert s.list_opportunities() == []
    finally:
        if kind == "sqlite":
            s.close()


@pytest.mark.parametrize("kind", ["sqlite", "memory"])
def test_get_opportunity_by_posting(kind, tmp_path):
    s = _make_store(kind, tmp_path)
    try:
        opp = new_opportunity({"title": "Gig", "source": "Verama", "source_uid": "V-1"})
        s.save_opportunity(opp)
        found = s.get_opportunity_by_posting("Verama", "V-1")
        assert found is not None and found.id == opp.id
        # unknown uid / unknown source / empty uid -> None
        assert s.get_opportunity_by_posting("Verama", "V-NOPE") is None
        assert s.get_opportunity_by_posting("OtherBoard", "V-1") is None
        assert s.get_opportunity_by_posting("Verama", "") is None
    finally:
        if kind == "sqlite":
            s.close()


@pytest.mark.parametrize("kind", ["sqlite", "memory"])
def test_update_opportunity_applies_mutator_atomically(kind, tmp_path):
    s = _make_store(kind, tmp_path)
    try:
        opp = new_opportunity({"title": "Gig"})
        s.save_opportunity(opp)

        def mutate(o):
            set_status(o, "qualifying")

        updated = s.update_opportunity(opp.id, mutate)
        assert updated is not None and updated.status == "qualifying"
        # the change is persisted (re-read from the store, not just the returned object)
        assert s.get_opportunity(opp.id).status == "qualifying"
        assert "status" in _event_types(s.get_opportunity(opp.id))
        # a missing id returns None
        assert s.update_opportunity("no-such-id", mutate) is None
    finally:
        if kind == "sqlite":
            s.close()


def test_sqlite_opportunity_survives_reopen_and_is_in_export(tmp_path):
    db = tmp_path / "opps.db"
    s1 = SqliteStore(db)
    opp = new_opportunity({"title": "Persisted Gig", "source": "Verama", "source_uid": "V-9"})
    set_staffing(opp, [{"consultant_id": "c1", "consultant_name": "Anna"}])
    s1.save_opportunity(opp)
    bundle = s1.export_all()
    assert "opportunities" in bundle
    assert any(o["id"] == opp.id for o in bundle["opportunities"])
    s1.close()

    # reopen a brand-new store over the same file — the opportunity must survive restart
    s2 = SqliteStore(db)
    got = s2.get_opportunity(opp.id)
    assert got is not None and got.title == "Persisted Gig"
    assert got.staffed and got.staffed[0]["consultant_id"] == "c1"
    assert s2.get_opportunity_by_posting("Verama", "V-9").id == opp.id
    s2.close()


# ===========================================================================
# (C) ENDPOINT — /api/opportunities ... (TestClient, like test_bench_web.py)
# ===========================================================================

JOB = {
    "title": "Senior Python Engineer",
    "description": "Build and ship Django REST APIs on AWS.",
    "source": "Verama",
    "source_uid": "OPP-TEST-1",
    "job_skills": ["python", "django", "aws"],
    "location": "Copenhagen",
}


def _create_consultant(**body) -> dict:
    r = client.post("/api/consultants", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def _delete_consultant(cid: str) -> None:
    client.delete(f"/api/consultants/{cid}")


def _create_opp(**body) -> dict:
    r = client.post("/api/opportunities", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def _delete_opp(oid: str) -> None:
    client.delete(f"/api/opportunities/{oid}")


def _event_types_from_payload(payload):
    return [e["type"] for e in payload["events"]]


def test_create_opportunity_from_job_and_idempotent_on_resubmit():
    job = {**JOB, "source_uid": "OPP-IDEMPOTENT-1"}
    first = _create_opp(job=job)
    try:
        assert first["id"]
        assert first["title"] == "Senior Python Engineer"
        assert first["source"] == "Verama" and first["source_uid"] == "OPP-IDEMPOTENT-1"
        # posting the SAME job again returns the SAME id (idempotent, no duplicate row)
        again = _create_opp(job=job)
        assert again["id"] == first["id"]
    finally:
        _delete_opp(first["id"])


def test_create_opportunity_requires_a_project():
    # no title/description/text/job -> 400
    assert client.post("/api/opportunities", json={}).status_code == 400


def test_create_opportunity_with_consultant_ids_staffs_and_logs_event():
    c = _create_consultant(name="Anna Jensen", skills=["python", "django", "aws"], title="Python Engineer")
    opp = None
    try:
        opp = _create_opp(
            title="Senior Python Engineer", description="Build Django APIs.",
            skills=["python", "django", "aws"], consultant_ids=[c["id"]],
        )
        assert opp["staffed"], "expected the opportunity to be staffed"
        assert opp["staffed"][0]["consultant_id"] == c["id"]
        assert "staffed" in _event_types_from_payload(opp)
    finally:
        if opp:
            _delete_opp(opp["id"])
        _delete_consultant(c["id"])


def test_list_get_patch_delete_lifecycle():
    opp = _create_opp(title="Lifecycle Gig", description="Some brief.")
    oid = opp["id"]
    try:
        # LIST includes it + the statuses catalog
        body = client.get("/api/opportunities").json()
        assert oid in {o["id"] for o in body["opportunities"]}
        assert "statuses" in body and set(STATUSES) <= set(body["statuses"])

        # GET real -> 200, missing -> 404
        assert client.get(f"/api/opportunities/{oid}").status_code == 200
        assert client.get("/api/opportunities/does-not-exist").status_code == 404

        # PATCH status persists + logs a "status" event
        r = client.patch(f"/api/opportunities/{oid}", json={"status": "qualifying"})
        assert r.status_code == 200
        assert r.json()["status"] == "qualifying"
        got = client.get(f"/api/opportunities/{oid}").json()
        assert got["status"] == "qualifying"
        assert "status" in _event_types_from_payload(got)

        # invalid status -> 400
        assert client.patch(f"/api/opportunities/{oid}", json={"status": "bogus"}).status_code == 400
    finally:
        # DELETE then GET -> 404
        d = client.delete(f"/api/opportunities/{oid}")
        assert d.status_code == 200 and d.json() == {"ok": True}
        assert client.get(f"/api/opportunities/{oid}").status_code == 404


def test_patch_missing_opportunity_is_404():
    assert client.patch("/api/opportunities/nope", json={"status": "qualifying"}).status_code == 404


def test_generate_proposal_into_opportunity_clean_template():
    c = _create_consultant(name="Anna Jensen", text="Senior Python Engineer\nSkills: Python, Django, AWS.",
                           skills=["python", "django", "aws"], title="Python Engineer")
    opp = None
    try:
        opp = _create_opp(title="Senior Python Engineer", description="Build Django APIs on AWS.",
                          skills=["python", "django", "aws"], consultant_ids=[c["id"]])
        r = client.post(f"/api/opportunities/{opp['id']}/proposal", json={})
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["blocking"] is False               # template is grounded
        # the opportunity now carries the proposal body + a "proposal_generated" event
        payload = data["opportunity"]
        assert payload["proposal_body"].strip()
        assert "proposal_generated" in _event_types_from_payload(payload)
        # status advanced to proposal_ready (not blocking)
        assert payload["status"] == "proposal_ready"
        # persisted: re-GET the opportunity and confirm the body survived
        got = client.get(f"/api/opportunities/{opp['id']}").json()
        assert got["proposal_body"].strip() and got["status"] == "proposal_ready"
    finally:
        if opp:
            _delete_opp(opp["id"])
        _delete_consultant(c["id"])


def test_generate_proposal_requires_a_staffed_consultant():
    opp = _create_opp(title="Unstaffed Gig", description="Nobody on it.")
    try:
        r = client.post(f"/api/opportunities/{opp['id']}/proposal", json={})
        assert r.status_code == 400
    finally:
        _delete_opp(opp["id"])


def test_export_clean_proposal_records_an_exported_event():
    c = _create_consultant(name="Anna Jensen", text="Senior Python Engineer\nSkills: Python, Django, AWS.",
                           skills=["python", "django", "aws"], title="Python Engineer")
    opp = None
    try:
        opp = _create_opp(title="Senior Python Engineer", description="Build Django APIs on AWS.",
                          skills=["python", "django", "aws"], consultant_ids=[c["id"]])
        gen = client.post(f"/api/opportunities/{opp['id']}/proposal", json={})
        assert gen.status_code == 200 and gen.json()["blocking"] is False

        r = client.get(f"/api/opportunities/{opp['id']}/export")
        assert r.status_code == 200, r.text
        assert "attachment" in r.headers.get("content-disposition", "")
        assert "Anna Jensen" in r.text                 # the grounded body carried through

        # the export recorded an "exported" audit event (re-GET and check the timeline)
        got = client.get(f"/api/opportunities/{opp['id']}").json()
        assert "exported" in _event_types_from_payload(got)
    finally:
        if opp:
            _delete_opp(opp["id"])
        _delete_consultant(c["id"])


def test_export_without_a_proposal_is_400():
    opp = _create_opp(title="No Proposal Gig", description="Nothing drafted.")
    try:
        r = client.get(f"/api/opportunities/{opp['id']}/export")
        assert r.status_code == 400
    finally:
        _delete_opp(opp["id"])


def test_export_blocks_a_fabricated_stored_proposal_with_409():
    """A clean template never fabricates, so the export-block path can't be reached through the
    generate endpoint alone. Stage it directly: staff a python-only consultant, then store a
    proposal body that claims a skill nobody on the bid has. Re-running the QA gate at export
    must refuse with 409 (an edited fabrication can't slip out)."""
    c = _create_consultant(name="Anna Jensen", skills=["python"], title="Python Engineer")
    opp = None
    try:
        opp = _create_opp(title="Platform Engineer", description="Run a platform.",
                          skills=["python"], consultant_ids=[c["id"]])
        # craft a fabricated stored proposal: Anna has only python; this claims Kubernetes.
        fabricated = ("Dear hiring team,\n\nWe put forward Anna Jensen, who has deep Kubernetes "
                      "expertise and years of Terraform experience.\n\nKind regards,\nThe House")
        patch = client.patch(
            f"/api/opportunities/{opp['id']}",
            json={"staffed": [{"consultant_id": c["id"], "consultant_name": "Anna Jensen"}]},
        )
        assert patch.status_code == 200
        # write the fabricated body straight onto the stored opportunity via the test store seam
        from jobfinder.web import store as _store
        from jobfinder.opportunities import attach_proposal as _attach
        updated = _store.update_opportunity(
            opp["id"],
            lambda o: _attach(o, "Proposal", fabricated, "template",
                              [{"type": "unsupported_capability", "blocking": True}], True),
        )
        assert updated is not None and updated.proposal_body == fabricated

        # export re-runs the gate against the staffed (python-only) consultant -> 409
        r = client.get(f"/api/opportunities/{opp['id']}/export")
        assert r.status_code == 409, r.text
        findings = r.json()["detail"]["findings"]
        assert "unsupported_capability" in {f["type"] for f in findings}, findings
        # and a blocked export must NOT record an "exported" event
        got = client.get(f"/api/opportunities/{opp['id']}").json()
        assert "exported" not in _event_types_from_payload(got)
    finally:
        if opp:
            _delete_opp(opp["id"])
        _delete_consultant(c["id"])


def test_attach_proposal_demotes_ready_when_blocking_replaces_clean():
    """A blocking proposal must never leave the opp at proposal_ready, even if a prior clean
    proposal advanced it there."""
    from jobfinder.opportunities import new_opportunity, attach_proposal
    opp = new_opportunity({"title": "X"})
    attach_proposal(opp, "s", "b", "template", [], blocking=False)
    assert opp.status == "proposal_ready"
    attach_proposal(opp, "s", "b2", "llm", [{"type": "unsupported_capability", "blocking": True}], blocking=True)
    assert opp.status == "proposal_drafting"


def test_new_opportunity_coerces_non_string_description():
    from jobfinder.opportunities import new_opportunity
    opp = new_opportunity({"title": "X", "description": 123})   # must not raise
    assert isinstance(opp.description, str)
