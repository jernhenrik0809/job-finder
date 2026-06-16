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
    assert cfg.default_sources == ["remotive", "arbeitnow"]   # LinkedIn no longer default
    assert isinstance(get_store(cfg), MemoryStore)
