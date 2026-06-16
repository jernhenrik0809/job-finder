"""Tests for the persistence layer: SQLite round-trip + restart survival, and config."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jobfinder.cv_parser import build_profile
from jobfinder.drafts import ApplicationDraft
from jobfinder.store.sqlite import SqliteStore
from jobfinder.store.memory import MemoryStore
from jobfinder.store import get_store
from jobfinder.config import load_settings

CV = "Jane Doe\nSenior Python Engineer\n8 years of experience. Skills: Python, Django, AWS."


def _draft(did="d1", title="Backend Engineer"):
    return ApplicationDraft(job_title=title, company="Acme", subject="Application for " + title,
                            body="Dear team, ...", generator="template", id=did)


def test_sqlite_persists_across_reopen(tmp_path):
    db = tmp_path / "jf.db"
    s1 = SqliteStore(db)
    s1.save_profile("cv1", build_profile(CV))
    s1.save_example({"id": "e1", "name": "ex", "text": "my letter", "chars": 9})
    s1.save_draft(_draft("d1"))
    s1.close()

    # Reopen a brand-new store over the same file — state must survive (the #1 fix).
    s2 = SqliteStore(db)
    prof = s2.get_profile("cv1")
    assert prof is not None and prof.name == "Jane Doe" and "python" in prof.skills
    assert [e["id"] for e in s2.list_examples()] == ["e1"]
    d = s2.get_draft("d1")
    assert d is not None and d.job_title == "Backend Engineer" and d.company == "Acme"
    s2.close()


def test_sqlite_update_preserves_order_and_edits(tmp_path):
    s = SqliteStore(tmp_path / "jf.db")
    s.save_draft(_draft("a", "A"))
    s.save_draft(_draft("b", "B"))
    # edit the first draft; order must stay [a, b] and the edit must persist
    d = s.get_draft("a"); d.status = "ready"; d.body = "edited"
    s.save_draft(d)
    drafts = s.list_drafts()
    assert [d.id for d in drafts] == ["a", "b"]
    assert s.get_draft("a").status == "ready" and s.get_draft("a").body == "edited"
    s.delete_draft("a")
    assert s.get_draft("a") is None and [d.id for d in s.list_drafts()] == ["b"]
    s.close()


def test_memory_store_basics():
    s = MemoryStore()
    s.save_profile("cv1", build_profile(CV))
    assert s.get_profile("cv1").name == "Jane Doe"
    s.save_draft(_draft("d1"))
    assert len(s.list_drafts()) == 1
    s.delete_draft("d1")
    assert s.list_drafts() == []


def test_factory_and_config_defaults(monkeypatch):
    monkeypatch.setenv("JOBFINDER_STORAGE", "memory")
    monkeypatch.delenv("JOBFINDER_DEFAULT_SOURCES", raising=False)
    cfg = load_settings()
    assert cfg.storage == "memory"
    assert cfg.default_sources == ["remotive", "arbeitnow"]   # LinkedIn no longer default
    assert isinstance(get_store(cfg), MemoryStore)
