"""Tests for the case-study layer (grounded proof / delivered engagements).

Three groups (mirrors test_clients.py):
  (A) UNIT  — ``jobfinder.case_studies`` factory, ``_clean_outcomes``, and the disclosure-aware
              ``display_client`` / ``is_renderable`` helpers, imported directly.
  (B) STORE — save/get/list/delete round-trip across BOTH backends, restart survival on
              SqliteStore, and that ``export_all()`` carries a "case_studies" section.
  (C) API   — the /api/case-studies CRUD endpoints, incl. the metric-less outcome being dropped,
              the unknown-disclosure-falls-back-to-confidential safety rule, the
              ``disclosure_levels`` catalogue on list, and consultant attribution.

State note (mirrors test_clients.py): the API group runs against the process-global in-memory
store forced by conftest, so each test seeds its OWN data and asserts on what it created (by id),
never on absolute table counts.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from fastapi.testclient import TestClient

from jobfinder.case_studies import (
    DISCLOSURE,
    CaseStudy,
    new_case_study,
    _clean_outcomes,
)
from jobfinder.store.sqlite import SqliteStore
from jobfinder.store.memory import MemoryStore
from jobfinder.web import app

client = TestClient(app)


# ===========================================================================
# (A) UNIT — case_studies.py factory + _clean_outcomes + display helpers
# ===========================================================================

def test_new_case_study_cleans_outcomes_and_falls_back_on_unknown_disclosure():
    cs = new_case_study(
        "X",
        outcomes=[
            {"metric": "cost saved", "value": 30, "unit": "%"},   # good -> kept (coerced)
            {"value": 99, "unit": "%"},                           # metric-less -> dropped
            "not-a-dict",                                         # non-dict -> dropped
        ],
        disclosure="bogus",                                       # unknown -> safe default
    )
    assert cs.title == "X"
    assert cs.created > 0 and cs.updated > 0
    assert cs.id                                                  # a generated id
    # only the metric-bearing outcome survives, with value/unit coerced to strings
    assert cs.outcomes == [{"metric": "cost saved", "value": "30", "unit": "%"}]
    # an UNKNOWN disclosure falls back to the safe default
    assert cs.disclosure == "confidential"


def test_new_case_study_blank_title_defaults_to_untitled():
    assert new_case_study("").title == "Untitled engagement"
    assert new_case_study("   ").title == "Untitled engagement"   # whitespace stripped first


def test_new_case_study_keeps_a_valid_disclosure():
    assert new_case_study("Y", disclosure="public").disclosure == "public"
    assert new_case_study("Y", disclosure="anonymized_only").disclosure == "anonymized_only"


def test_clean_outcomes_keeps_only_metric_bearing_dicts_and_coerces():
    cleaned = _clean_outcomes([
        {"metric": "  uptime  ", "value": 99.9, "unit": None},    # coerce value, drop None unit
        {"metric": "", "value": "x"},                            # blank metric -> dropped
        {"value": "5", "unit": "ms"},                            # no metric -> dropped
        "not-a-dict",                                            # non-dict -> dropped
        None,                                                    # non-dict -> dropped
        {"metric": "throughput"},                               # only a metric -> blanks filled
    ])
    assert cleaned == [
        {"metric": "uptime", "value": "99.9", "unit": ""},
        {"metric": "throughput", "value": "", "unit": ""},
    ]
    # every coerced field is a string
    for o in cleaned:
        assert all(isinstance(v, str) for v in o.values())


def test_clean_outcomes_handles_none_and_empty():
    assert _clean_outcomes(None) == []
    assert _clean_outcomes([]) == []


def test_display_client_respects_disclosure():
    # public -> the real client name is shown
    public = CaseStudy(title="T", client_name="Globex A/S",
                       client_anonymized="a manufacturer", disclosure="public")
    assert public.display_client() == "Globex A/S"

    # anonymized_only -> never the real name, fall back to the anonymized descriptor
    anon = CaseStudy(title="T", client_name="Globex A/S",
                     client_anonymized="a manufacturer", disclosure="anonymized_only")
    assert anon.display_client() == "a manufacturer"

    # confidential with no anonymized descriptor -> the generic "a client" placeholder
    conf = CaseStudy(title="T", client_name="Globex A/S", disclosure="confidential")
    assert conf.display_client() == "a client"


def test_is_renderable_blocks_confidential_only():
    assert CaseStudy(title="T", disclosure="public").is_renderable() is True
    assert CaseStudy(title="T", disclosure="anonymized_only").is_renderable() is True
    assert CaseStudy(title="T", disclosure="confidential").is_renderable() is False


def test_from_dict_ignores_unknown_keys():
    cs = CaseStudy.from_dict({
        "title": "Imported",
        "disclosure": "public",
        "consultant_ids": ["c1", "c2"],
        "some_future_field": 123,        # unknown -> ignored, must not raise
    })
    assert cs.title == "Imported" and cs.disclosure == "public"
    assert cs.consultant_ids == ["c1", "c2"]
    assert not hasattr(cs, "some_future_field")


# ===========================================================================
# (B) STORE — round-trip on both backends + sqlite restart survival
# ===========================================================================

def test_case_study_round_trip_both_backends(tmp_path):
    for store in (SqliteStore(tmp_path / "cs.db"), MemoryStore()):
        try:
            cs = new_case_study(
                "GDPR platform",
                sector="pensions",
                client_anonymized="a Danish pension provider",
                disclosure="anonymized_only",
                outcomes=[{"metric": "cost saved", "value": 30, "unit": "%"}],
                consultant_ids=["c1", "c2"],
            )
            store.save_case_study(cs)

            got = store.get_case_study(cs.id)
            assert got is not None
            assert got.title == "GDPR platform" and got.sector == "pensions"
            assert got.disclosure == "anonymized_only"
            # outcomes survive the round-trip intact (coerced to strings)
            assert got.outcomes == [{"metric": "cost saved", "value": "30", "unit": "%"}]
            # consultant attribution survives
            assert got.consultant_ids == ["c1", "c2"]

            assert [x.id for x in store.list_case_studies()] == [cs.id]

            store.delete_case_study(cs.id)
            assert store.get_case_study(cs.id) is None
            assert store.list_case_studies() == []
        finally:
            if isinstance(store, SqliteStore):
                store.close()


def test_case_study_survives_sqlite_reopen(tmp_path):
    db = tmp_path / "cs.db"
    s1 = SqliteStore(db)
    cs = new_case_study("Cloud migration", sector="banking", disclosure="public",
                        client_name="Initech",
                        outcomes=[{"metric": "latency", "value": 40, "unit": "ms"}],
                        consultant_ids=["c9"])
    s1.save_case_study(cs)
    s1.close()

    s2 = SqliteStore(db)                              # reopen a brand-new store over the same file
    got = s2.get_case_study(cs.id)
    assert got is not None and got.title == "Cloud migration" and got.sector == "banking"
    assert got.disclosure == "public" and got.client_name == "Initech"
    assert got.outcomes == [{"metric": "latency", "value": "40", "unit": "ms"}]
    assert got.consultant_ids == ["c9"]
    assert [x.id for x in s2.list_case_studies()] == [cs.id]
    s2.close()


def test_export_all_includes_case_studies_key(tmp_path):
    s = SqliteStore(tmp_path / "cs.db")
    try:
        s.save_case_study(new_case_study("GDPR platform", disclosure="anonymized_only",
                                         client_anonymized="a Danish pension provider"))
        bundle = s.export_all()
        assert "case_studies" in bundle
        assert len(bundle["case_studies"]) == 1
        assert bundle["case_studies"][0]["title"] == "GDPR platform"
    finally:
        s.close()


# ===========================================================================
# (C) API — endpoints, outcome cleaning, disclosure safety, attribution
# ===========================================================================

def _create_case_study(**body) -> dict:
    r = client.post("/api/case-studies", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def _delete_case_study(csid: str) -> None:
    client.delete(f"/api/case-studies/{csid}")


# --- POST /api/case-studies -----------------------------------------------

def test_post_case_study_drops_metric_less_outcome_and_persists_disclosure():
    cs = _create_case_study(
        title="Payments revamp", sector="fintech",
        client_anonymized="a Nordic bank",
        disclosure="anonymized_only",
        outcomes=[
            {"metric": "throughput", "value": 2, "unit": "x"},   # valid -> kept
            {"value": 5, "unit": "ms"},                          # metric-less -> dropped
        ],
    )
    try:
        assert cs["id"]
        assert cs["title"] == "Payments revamp" and cs["sector"] == "fintech"
        assert cs["disclosure"] == "anonymized_only"
        # only the metric-bearing outcome survives, coerced to strings
        assert cs["outcomes"] == [{"metric": "throughput", "value": "2", "unit": "x"}]
        # round-trips through the store, not just the response object
        got = client.get(f"/api/case-studies/{cs['id']}").json()
        assert got["disclosure"] == "anonymized_only" and len(got["outcomes"]) == 1
    finally:
        _delete_case_study(cs["id"])


def test_post_case_study_invalid_disclosure_falls_back_to_confidential():
    cs = _create_case_study(title="Mystery engagement", disclosure="totally-bogus")
    try:
        assert cs["disclosure"] == "confidential"          # unknown -> safe default
        got = client.get(f"/api/case-studies/{cs['id']}").json()
        assert got["disclosure"] == "confidential"
    finally:
        _delete_case_study(cs["id"])


def test_post_case_study_persists_consultant_attribution():
    cs = _create_case_study(title="Attributed engagement",
                            consultant_ids=["c1", "c2", "c3"])
    try:
        assert cs["consultant_ids"] == ["c1", "c2", "c3"]
        got = client.get(f"/api/case-studies/{cs['id']}").json()
        assert got["consultant_ids"] == ["c1", "c2", "c3"]
    finally:
        _delete_case_study(cs["id"])


# --- GET /api/case-studies + /{id} ----------------------------------------

def test_list_includes_it_and_disclosure_levels():
    cs = _create_case_study(title="Listed engagement", disclosure="public")
    try:
        body = client.get("/api/case-studies").json()
        ids = {x["id"] for x in body["case_studies"]}
        assert cs["id"] in ids                       # the one we created shows up
        # the create form needs the disclosure catalogue to render its dropdown
        assert body["disclosure_levels"] == list(DISCLOSURE)
    finally:
        _delete_case_study(cs["id"])


def test_get_case_study_real_and_missing():
    cs = _create_case_study(title="Fetchable engagement")
    try:
        got = client.get(f"/api/case-studies/{cs['id']}")
        assert got.status_code == 200 and got.json()["id"] == cs["id"]
        assert client.get("/api/case-studies/does-not-exist").status_code == 404
    finally:
        _delete_case_study(cs["id"])


# --- PATCH /api/case-studies/{id} -----------------------------------------

def test_patch_case_study_persists_changes():
    cs = _create_case_study(title="Patchable engagement", disclosure="confidential",
                            summary="old summary")
    try:
        r = client.patch(f"/api/case-studies/{cs['id']}",
                         json={"disclosure": "public", "summary": "new summary"})
        assert r.status_code == 200
        upd = r.json()
        assert upd["disclosure"] == "public" and upd["summary"] == "new summary"
        # persisted (re-read from the store)
        got = client.get(f"/api/case-studies/{cs['id']}").json()
        assert got["disclosure"] == "public" and got["summary"] == "new summary"
    finally:
        _delete_case_study(cs["id"])


def test_patch_case_study_missing_is_404():
    assert client.patch("/api/case-studies/nope", json={"summary": "x"}).status_code == 404


# --- DELETE /api/case-studies/{id} ----------------------------------------

def test_delete_case_study_then_get_is_404():
    cs = _create_case_study(title="Delete engagement")
    r = client.delete(f"/api/case-studies/{cs['id']}")
    assert r.status_code == 200 and r.json() == {"ok": True}
    assert client.get(f"/api/case-studies/{cs['id']}").status_code == 404
