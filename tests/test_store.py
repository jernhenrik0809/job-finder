"""Tests for the persistence layer: SQLite round-trip + restart survival, and config."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jobfinder.applications import Application, set_status
from jobfinder.cv_parser import build_profile
from jobfinder.store.sqlite import SqliteStore
from jobfinder.store.memory import MemoryStore
from jobfinder.store import get_store
from jobfinder.config import load_settings

CV = "Jane Doe\nSenior Python Engineer\n8 years of experience. Skills: Python, Django, AWS."


def _app(aid="a1", title="Backend Engineer"):
    return Application(job_title=title, company="Acme", id=aid, status="saved",
                       subject="Application for " + title, body="Dear team, ...")


def test_sqlite_persists_across_reopen(tmp_path):
    db = tmp_path / "jf.db"
    s1 = SqliteStore(db)
    s1.save_profile("cv1", build_profile(CV))
    s1.save_example({"id": "e1", "name": "ex", "text": "my letter", "chars": 9})
    s1.save_application(_app("a1"))
    s1.close()

    # Reopen a brand-new store over the same file — state must survive (the #1 fix).
    s2 = SqliteStore(db)
    prof = s2.get_profile("cv1")
    assert prof is not None and prof.name == "Jane Doe" and "python" in prof.skills
    assert [e["id"] for e in s2.list_examples()] == ["e1"]
    a = s2.get_application("a1")
    assert a is not None and a.job_title == "Backend Engineer" and a.company == "Acme"
    s2.close()


def test_sqlite_update_preserves_order_and_edits(tmp_path):
    s = SqliteStore(tmp_path / "jf.db")
    s.save_application(_app("a", "A"))
    s.save_application(_app("b", "B"))
    a = s.get_application("a"); set_status(a, "ready"); a.body = "edited"
    s.save_application(a)
    apps = s.list_applications()
    assert [x.id for x in apps] == ["a", "b"]
    assert s.get_application("a").status == "ready" and s.get_application("a").body == "edited"
    s.delete_application("a")
    assert s.get_application("a") is None and [x.id for x in s.list_applications()] == ["b"]
    s.close()


def test_sqlite_concurrent_read_write(tmp_path):
    # Regression for the shared-connection corruption: concurrent reads + writes across
    # threads (as FastAPI's threadpool does) must not raise or corrupt data.
    import threading
    s = SqliteStore(tmp_path / "jf.db")
    s.save_application(_app("seed"))
    errors: list[Exception] = []
    stop = threading.Event()

    def reader():
        while not stop.is_set():
            try:
                s.list_applications(); s.get_application("seed"); s.list_examples()
            except Exception as e:
                errors.append(e); return

    def writer(n):
        for i in range(40):
            try:
                s.save_application(_app(f"w{n}-{i}", f"Role {i}"))
                s.save_example({"id": f"e{n}-{i}", "name": "x", "text": "y", "chars": 1})
            except Exception as e:
                errors.append(e); return

    threads = [threading.Thread(target=reader) for _ in range(4)] + \
              [threading.Thread(target=writer, args=(n,)) for n in range(3)]
    for t in threads[4:]:
        t.start()
    for t in threads[:4]:
        t.start()
    for t in threads[4:]:
        t.join()
    stop.set()
    for t in threads[:4]:
        t.join()
    s.close()
    assert not errors, f"concurrency errors: {errors[:3]}"


def test_sqlite_v1_drafts_migrate_to_applications(tmp_path):
    # A v1.1.0 DB stored cover letters in a 'drafts' table at schema_version=1.
    # Opening it with the current store must carry them into 'applications', not orphan them.
    import sqlite3, json
    db = tmp_path / "jf.db"
    conn = sqlite3.connect(str(db))
    conn.executescript("""
        CREATE TABLE profiles (cv_id TEXT PRIMARY KEY, created REAL, data TEXT);
        CREATE TABLE examples (id TEXT PRIMARY KEY, created REAL, name TEXT, text TEXT, chars INTEGER);
        CREATE TABLE drafts (id TEXT PRIMARY KEY, created REAL, data TEXT);
        CREATE TABLE schema_version (version INTEGER);
    """)
    conn.execute("INSERT INTO schema_version(version) VALUES(1)")
    draft = {"job_title": "Old Role", "company": "OldCo", "job_url": "https://x/1", "job_source": "LinkedIn",
             "score": 80.0, "subject": "Application for Old Role", "body": "Dear team...",
             "generator": "template", "status": "ready", "note": "", "id": "old1"}
    conn.execute("INSERT INTO drafts(id, created, data) VALUES(?,?,?)", ("old1", 1000.0, json.dumps(draft)))
    conn.commit(); conn.close()

    s = SqliteStore(db)
    apps = s.list_applications()
    assert len(apps) == 1
    a = apps[0]
    assert a.id == "old1" and a.job_title == "Old Role" and a.company == "OldCo"
    assert a.status == "ready" and a.body == "Dear team..." and a.generator == "template"
    assert any(e["type"] == "migrated" for e in a.events)
    from jobfinder.store.sqlite import _SCHEMA_VERSION
    ver = s._conn.execute("SELECT version FROM schema_version").fetchone()["version"]
    assert ver == _SCHEMA_VERSION                # bumped to the current schema (drafts carried over)
    assert s._conn.execute("SELECT name FROM sqlite_master WHERE name='drafts'").fetchone() is None
    s.close()


def test_application_from_dict_ignores_unknown_fields(tmp_path):
    # One row carrying a field the current dataclass doesn't know must not 500 the list endpoint.
    import json
    s = SqliteStore(tmp_path / "jf.db")
    blob = _app("x1").to_dict(); blob["some_future_field"] = 123
    s._conn.execute("INSERT INTO applications(id, created, data) VALUES(?,?,?)", ("x1", 1.0, json.dumps(blob)))
    s._conn.commit()
    apps = s.list_applications()        # must not raise
    assert len(apps) == 1 and apps[0].id == "x1"
    assert s.get_application("x1") is not None
    s.close()


def test_sqlite_saved_search_round_trip(tmp_path):
    from jobfinder.saved_searches import new_saved_search, register_run
    s = SqliteStore(tmp_path / "jf.db")
    ss = new_saved_search("My search", {"cv_id": "cv1", "keywords": "python", "sources": ["remotive"]})
    register_run(ss, ["a", "b"])
    s.save_saved_search(ss)
    s.close()

    s2 = SqliteStore(tmp_path / "jf.db")
    got = s2.get_saved_search(ss.id)
    assert got and got.name == "My search" and got.new_count == 2 and set(got.seen_ids) == {"a", "b"}
    assert [x.id for x in s2.list_saved_searches()] == [ss.id]
    s2.delete_saved_search(ss.id)
    assert s2.get_saved_search(ss.id) is None
    s2.close()


def test_export_and_delete_all(tmp_path):
    from jobfinder.saved_searches import new_saved_search
    from jobfinder.notifications import Notification
    s = SqliteStore(tmp_path / "jf.db")
    s.save_profile("cv1", build_profile(CV))
    s.save_application(_app("a1"))
    s.save_saved_search(new_saved_search("S", {"cv_id": "cv1", "keywords": "py"}))
    s.save_notification(Notification(kind="reminder", title="T", created=1.0))

    bundle = s.export_all()
    assert "cv1" in bundle["profiles"] and len(bundle["applications"]) == 1
    assert len(bundle["saved_searches"]) == 1 and len(bundle["notifications"]) == 1

    s.delete_all()
    empty = s.export_all()
    assert all(not v for v in empty.values())        # every section emptied (robust to new tables)
    assert s.get_profile("cv1") is None and s.list_applications() == []
    s.close()


def test_export_delete_all_covers_every_table(tmp_path):
    """Reflective data-rights guard: every user-data table must appear in export_all() and be
    emptied by delete_all(), so a newly-added entity can't silently escape export/erasure."""
    from jobfinder.saved_searches import new_saved_search
    from jobfinder.notifications import Notification
    from jobfinder.consultants import Consultant
    from jobfinder.house import House
    from jobfinder.opportunities import new_opportunity
    from jobfinder.clients import new_client
    from jobfinder.case_studies import new_case_study
    s = SqliteStore(tmp_path / "jf.db")
    s.save_profile("cv1", build_profile(CV))
    s.save_example({"id": "e1", "name": "ex", "text": "t", "chars": 1})
    s.save_application(_app("a1"))
    s.save_saved_search(new_saved_search("S", {"cv_id": "cv1", "keywords": "py"}))
    s.save_notification(Notification(kind="reminder", title="T", created=1.0))
    s.save_consultant(Consultant(name="Anna", id="c1", skills=["python"]))
    s.save_house(House(name="Acme Consulting"))
    s.save_opportunity(new_opportunity({"title": "Gig", "source": "Verama", "source_uid": "V-1"}))
    s.save_client(new_client("Globex", sector="fintech"))
    s.save_case_study(new_case_study("GDPR platform", disclosure="anonymized_only",
                                     client_anonymized="a Danish pension provider"))

    tables = {r["name"] for r in s._conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    tables -= {"schema_version", "sqlite_sequence"}
    bundle = s.export_all()
    for t in tables:
        assert t in bundle, f"table {t!r} missing from export_all()"
        assert bundle[t], f"table {t!r} populated but missing/empty in export_all()"

    s.delete_all()
    empty = s.export_all()
    for t in tables:
        assert not empty[t], f"table {t!r} not emptied by delete_all()"
    s.close()


def test_consultant_and_house_round_trip(tmp_path):
    from jobfinder.consultants import Consultant, new_consultant
    from jobfinder.house import House, HOUSE_ID
    db = tmp_path / "jf.db"
    s1 = SqliteStore(db)
    c = new_consultant("Lars Holm", id="c1", skills=["python", "aws"], seniority="senior",
                       engagement_type="subcontractor", cost_rate=600.0, sell_rate=950.0,
                       currency="DKK", data_origin="third_party", right_to_present=True)
    s1.save_consultant(c)
    s1.save_house(House(name="Nordic Consulting", voice="pragmatic", signatory="Jane, Partner"))
    s1.close()

    s2 = SqliteStore(db)                              # reopen: bench survives restart
    got = s2.get_consultant("c1")
    assert got is not None and got.name == "Lars Holm" and got.engagement_type == "subcontractor"
    assert got.cost_rate == 600.0 and got.currency == "DKK" and got.data_origin == "third_party"
    assert [x.id for x in s2.list_consultants()] == ["c1"]
    h = s2.get_house()
    assert h is not None and h.id == HOUSE_ID and h.name == "Nordic Consulting"
    # save_house enforces the single-row id even if a different id is passed
    s2.save_house(House(name="Renamed", id="bogus"))
    assert s2.get_house().name == "Renamed" and s2.get_house().id == HOUSE_ID
    s2.delete_consultant("c1")
    assert s2.get_consultant("c1") is None
    s2.close()


def test_memory_store_basics():
    s = MemoryStore()
    s.save_profile("cv1", build_profile(CV))
    assert s.get_profile("cv1").name == "Jane Doe"
    s.save_application(_app("a1"))
    assert len(s.list_applications()) == 1
    s.delete_application("a1")
    assert s.list_applications() == []


def test_factory_and_config_defaults(monkeypatch):
    monkeypatch.setenv("JOBFINDER_STORAGE", "memory")
    monkeypatch.delenv("JOBFINDER_DEFAULT_SOURCES", raising=False)
    cfg = load_settings()
    assert cfg.storage == "memory"
    assert cfg.default_sources == ["remotive", "arbeitnow", "thehub", "themuse", "itjobbank", "hrmanager"]   # no-key DK-relevant
    assert isinstance(get_store(cfg), MemoryStore)


def test_notification_order_parity_after_refresh(tmp_path):
    """MemoryStore and SqliteStore must agree on newest-first-by-created order, even after an
    in-place refresh bumps a notification's created timestamp."""
    from jobfinder.notifications import Notification
    from jobfinder.store.memory import MemoryStore
    for s in (SqliteStore(tmp_path / "jf.db"), MemoryStore()):
        s.save_notification(Notification(kind="reminder", title="r1", id="r1", created=100.0))
        s.save_notification(Notification(kind="reminder", title="r2", id="r2", created=200.0))
        s.save_notification(Notification(kind="reminder", title="r1", id="r1", created=300.0))  # refresh r1
        order = [n.id for n in s.list_notifications()]
        assert order == ["r1", "r2"], f"{type(s).__name__} order {order}"
        if hasattr(s, "close"):
            s.close()
