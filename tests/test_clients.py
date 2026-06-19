"""Tests for the clients layer (the direct-warm relationship records) + the opportunity
commercials it sits next to.

Three groups:
  (A) UNIT  — ``jobfinder.clients`` factory + contact cleaning, imported directly.
  (B) STORE — save/get/list/delete round-trip across BOTH backends, restart survival on
              SqliteStore, and that ``export_all()`` carries a "clients" section.
  (C) API   — the /api/clients CRUD endpoints, the per-line / total margin payload on
              opportunities (incl. the no-cross-FX-sum rule), and client<->opportunity linking.

State note (mirrors test_bench_web.py): the API group runs against the process-global
in-memory store forced by conftest, so each test seeds its OWN data and asserts on what it
created (by id), never on absolute table counts.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from fastapi.testclient import TestClient

from jobfinder.clients import Client, new_client, _clean_contacts
from jobfinder.store.sqlite import SqliteStore
from jobfinder.store.memory import MemoryStore
from jobfinder.web import app

client = TestClient(app)


# ===========================================================================
# (A) UNIT — clients.py factory + _clean_contacts
# ===========================================================================

def test_new_client_sets_fields_and_cleans_contacts():
    c = new_client(
        "Globex",
        contacts=[
            {"name": "Ada Lovelace", "role": "CTO", "email": "ada@globex.com", "phone": "123"},
            {"role": "no name here"},          # nameless -> dropped
        ],
        do_not_bid=True,
    )
    assert c.name == "Globex"
    assert c.do_not_bid is True
    assert c.created > 0 and c.updated > 0
    assert c.id                                   # a generated id
    # only the well-formed contact survives
    assert c.contacts == [
        {"name": "Ada Lovelace", "role": "CTO", "email": "ada@globex.com", "phone": "123"},
    ]


def test_new_client_blank_name_defaults_to_unnamed():
    assert new_client("").name == "Unnamed client"
    assert new_client("   ").name == "Unnamed client"      # whitespace is stripped first


def test_clean_contacts_keeps_only_named_dicts_and_coerces_to_strings():
    cleaned = _clean_contacts([
        {"name": "  Grace  ", "role": 5, "email": None, "phone": 42},  # coerce role/phone, drop None
        {"name": "", "role": "x"},                                     # blank name -> dropped
        {"role": "nameless"},                                          # no name -> dropped
        "not-a-dict",                                                  # non-dict -> dropped
        None,                                                          # non-dict -> dropped
        {"name": "Linus"},                                             # only a name -> blanks filled
    ])
    assert cleaned == [
        {"name": "Grace", "role": "5", "email": "", "phone": "42"},
        {"name": "Linus", "role": "", "email": "", "phone": ""},
    ]
    # every coerced value is a string
    for ct in cleaned:
        assert all(isinstance(v, str) for v in ct.values())


def test_clean_contacts_handles_none_and_empty():
    assert _clean_contacts(None) == []
    assert _clean_contacts([]) == []


# ===========================================================================
# (B) STORE — round-trip on both backends + sqlite restart survival
# ===========================================================================

def test_client_round_trip_both_backends(tmp_path):
    for store in (SqliteStore(tmp_path / "clients.db"), MemoryStore()):
        try:
            c = new_client("Initech", sector="fintech",
                           contacts=[{"name": "Bill", "role": "Boss"}], do_not_bid=True)
            store.save_client(c)

            got = store.get_client(c.id)
            assert got is not None
            assert got.name == "Initech" and got.sector == "fintech"
            assert got.do_not_bid is True
            assert got.contacts == [{"name": "Bill", "role": "Boss", "email": "", "phone": ""}]

            assert [x.id for x in store.list_clients()] == [c.id]

            store.delete_client(c.id)
            assert store.get_client(c.id) is None
            assert store.list_clients() == []
        finally:
            if isinstance(store, SqliteStore):
                store.close()


def test_client_survives_sqlite_reopen(tmp_path):
    db = tmp_path / "clients.db"
    s1 = SqliteStore(db)
    c = new_client("Soylent", sector="food", do_not_bid=True,
                   contacts=[{"name": "Carol", "email": "carol@soylent.test"}])
    s1.save_client(c)
    s1.close()

    s2 = SqliteStore(db)                               # reopen a brand-new store over the same file
    got = s2.get_client(c.id)
    assert got is not None and got.name == "Soylent" and got.sector == "food"
    assert got.do_not_bid is True
    assert got.contacts == [{"name": "Carol", "role": "", "email": "carol@soylent.test", "phone": ""}]
    assert [x.id for x in s2.list_clients()] == [c.id]
    s2.close()


def test_export_all_includes_clients_key(tmp_path):
    s = SqliteStore(tmp_path / "clients.db")
    try:
        s.save_client(new_client("Globex", sector="fintech"))
        bundle = s.export_all()
        assert "clients" in bundle
        assert len(bundle["clients"]) == 1
        assert bundle["clients"][0]["name"] == "Globex"
    finally:
        s.close()


# ===========================================================================
# (C) API — endpoints, margin payload, and linking
# ===========================================================================

def _create_client(**body) -> dict:
    r = client.post("/api/clients", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def _delete_client(cid: str) -> None:
    client.delete(f"/api/clients/{cid}")


def _create_consultant(**body) -> dict:
    r = client.post("/api/consultants", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def _delete_consultant(cid: str) -> None:
    client.delete(f"/api/consultants/{cid}")


def _create_opportunity(**body) -> dict:
    r = client.post("/api/opportunities", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def _delete_opportunity(oid: str) -> None:
    client.delete(f"/api/opportunities/{oid}")


# --- POST /api/clients ----------------------------------------------------

def test_post_client_drops_nameless_contact_and_persists_do_not_bid():
    c = _create_client(
        name="Acme Corp", sector="manufacturing",
        contacts=[
            {"name": "Wile E.", "role": "Buyer", "email": "wile@acme.test"},
            {"role": "nameless contact"},          # dropped by _clean_contacts
        ],
        do_not_bid=True,
    )
    try:
        assert c["id"]
        assert c["name"] == "Acme Corp" and c["sector"] == "manufacturing"
        assert c["do_not_bid"] is True
        # only the named contact survives, coerced to the full {name, role, email, phone} shape
        assert c["contacts"] == [
            {"name": "Wile E.", "role": "Buyer", "email": "wile@acme.test", "phone": ""},
        ]
        # round-trips through the store, not just the response object
        got = client.get(f"/api/clients/{c['id']}").json()
        assert got["do_not_bid"] is True and len(got["contacts"]) == 1
    finally:
        _delete_client(c["id"])


# --- GET /api/clients + /{id} ---------------------------------------------

def test_list_and_get_client_real_and_missing():
    c = _create_client(name="Listed Account")
    try:
        ids = {x["id"] for x in client.get("/api/clients").json()["clients"]}
        assert c["id"] in ids                       # the one we created shows up

        got = client.get(f"/api/clients/{c['id']}")
        assert got.status_code == 200 and got.json()["id"] == c["id"]

        assert client.get("/api/clients/does-not-exist").status_code == 404
    finally:
        _delete_client(c["id"])


# --- PATCH /api/clients/{id} ----------------------------------------------

def test_patch_client_persists_changes():
    c = _create_client(name="Patch Account", sector="retail", do_not_bid=True)
    try:
        r = client.patch(f"/api/clients/{c['id']}", json={"do_not_bid": False, "sector": "banking"})
        assert r.status_code == 200
        upd = r.json()
        assert upd["do_not_bid"] is False and upd["sector"] == "banking"
        # persisted (re-read from the store)
        got = client.get(f"/api/clients/{c['id']}").json()
        assert got["do_not_bid"] is False and got["sector"] == "banking"
    finally:
        _delete_client(c["id"])


def test_patch_client_missing_is_404():
    assert client.patch("/api/clients/nope", json={"sector": "x"}).status_code == 404


# --- DELETE /api/clients/{id} ---------------------------------------------

def test_delete_client_then_get_is_404():
    c = _create_client(name="Delete Account")
    r = client.delete(f"/api/clients/{c['id']}")
    assert r.status_code == 200 and r.json() == {"ok": True}
    assert client.get(f"/api/clients/{c['id']}").status_code == 404


# --- Margin payload on opportunities --------------------------------------

def test_opportunity_margin_single_currency_sums():
    con = _create_consultant(name="Margin One", cost_rate=600, sell_rate=950, currency="DKK")
    try:
        opp = _create_opportunity(title="DKK Gig", consultant_ids=[con["id"]])
        try:
            # use the create response, then confirm GET reflects the same commercials
            for payload in (opp, client.get(f"/api/opportunities/{opp['id']}").json()):
                assert len(payload["staffed"]) == 1
                line = payload["staffed"][0]
                assert line["consultant_id"] == con["id"]
                assert line["margin"] == 350                 # 950 sell - 600 cost
                assert payload["total_margin"] == 350
                assert payload["margin_currency"] == "DKK"
        finally:
            _delete_opportunity(opp["id"])
    finally:
        _delete_consultant(con["id"])


def test_opportunity_total_margin_null_across_currencies_but_lines_present():
    dkk = _create_consultant(name="DKK Person", cost_rate=600, sell_rate=950, currency="DKK")
    eur = _create_consultant(name="EUR Person", cost_rate=80, sell_rate=130, currency="EUR")
    try:
        opp = _create_opportunity(title="Mixed FX Gig", consultant_ids=[dkk["id"], eur["id"]])
        try:
            payload = client.get(f"/api/opportunities/{opp['id']}").json()
            lines = {ln["consultant_id"]: ln for ln in payload["staffed"]}
            # per-line margins are still computed (each within its own currency)
            assert lines[dkk["id"]]["margin"] == 350         # 950 - 600
            assert lines[eur["id"]]["margin"] == 50          # 130 - 80
            # but no cross-FX sum: total is null and the currency label is blank
            assert payload["total_margin"] is None
            assert payload["margin_currency"] == ""
        finally:
            _delete_opportunity(opp["id"])
    finally:
        _delete_consultant(dkk["id"])
        _delete_consultant(eur["id"])


# --- Linking an opportunity to a client -----------------------------------

def test_patch_opportunity_persists_client_id():
    acc = _create_client(name="Linked Account")
    opp = _create_opportunity(title="Linkable Gig")
    try:
        r = client.patch(f"/api/opportunities/{opp['id']}", json={"client_id": acc["id"]})
        assert r.status_code == 200
        assert r.json()["client_id"] == acc["id"]
        # persisted (re-read from the store)
        got = client.get(f"/api/opportunities/{opp['id']}").json()
        assert got["client_id"] == acc["id"]
    finally:
        _delete_opportunity(opp["id"])
        _delete_client(acc["id"])
