"""Tests for the opt-in alerts sweep, the notification inbox, prefs, and the API.

No real network: a fake find_jobs feeds deterministic results into run_sweep.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from fastapi.testclient import TestClient

import jobfinder.alerts as alerts
import jobfinder.web as web
from jobfinder.applications import Application
from jobfinder.cv_parser import build_profile
from jobfinder.notifications import Notification
from jobfinder.saved_searches import new_saved_search
from jobfinder.store.memory import MemoryStore

_DAY = 86400.0
CV = "Jane Doe\nSenior Python Engineer\nSkills: Python, Django, AWS."


class _Job:
    def __init__(self, jid, title="Role"):
        self.id, self.title = jid, title

    def to_dict(self):
        return {"id": self.id, "title": self.title, "company": "Acme", "location": "Remote",
                "url": f"https://x/{self.id}", "source": "remotive", "posted": "2026-06-17", "score": 70}


class _Result:
    def __init__(self, jobs):
        self.jobs, self.warnings, self.counts = jobs, [], {}


def _store_with_search(job_ids=("j1", "j2")):
    store = MemoryStore()
    store.save_profile("cv1", build_profile(CV))
    s = new_saved_search("Py jobs", {"cv_id": "cv1", "keywords": "python", "sources": ["remotive"]})
    store.save_saved_search(s)
    fake = lambda profile, settings_: _Result([_Job(j) for j in job_ids])
    return store, s, fake


# --- sweep: new matches ---------------------------------------------------

def test_sweep_raises_new_matches_then_is_idempotent():
    store, s, fake = _store_with_search()
    summary = alerts.run_sweep(store, fake, now=1000.0)
    assert summary["searches_run"] == 1 and summary["new_matches"] == 2
    notes = store.list_notifications()
    assert len(notes) == 1 and notes[0].kind == "new_matches" and notes[0].count == 2
    assert len(notes[0].jobs) == 2 and notes[0].jobs[0]["url"].startswith("https://x/")

    # second sweep with the same results → nothing new (ids already seen), no new notification
    summary2 = alerts.run_sweep(store, fake, now=2000.0)
    assert summary2["new_matches"] == 0
    assert len(store.list_notifications()) == 1


# --- sweep: consulting bench-fit overlay ----------------------------------

class _GigJob:
    def __init__(self):
        self.id = "g1"
        self.title = "Senior Python Consultant"
        self.description = "Build Django REST APIs on AWS"
        self.job_skills = ["python", "django", "aws"]
        self.location = "Copenhagen"
        self.remote = False
        self.source = "Verama"
        self.url = "https://x/g1"

    def to_dict(self):
        return {"id": self.id, "title": self.title, "company": "Verama", "location": self.location,
                "url": self.url, "source": self.source, "posted": "2026-06-17", "score": 70}


def test_sweep_raises_bench_fit_with_bid_no_bid():
    from jobfinder.consultants import new_consultant
    store = MemoryStore()
    store.save_profile("cv1", build_profile(CV))
    store.save_saved_search(new_saved_search("DK gigs", {"cv_id": "cv1", "keywords": "python",
                                                         "sources": ["remotive"], "gigs_only": True}))
    store.save_consultant(new_consultant("Anna Berg", skills=["python", "django", "aws"],
                                         raw_text="Senior Python, Django and AWS engineer, 8 years."))
    store.save_consultant(new_consultant("Bo Java", skills=["java"], raw_text="Java developer."))
    fake = lambda p, s: _Result([_GigJob()])

    summary = alerts.run_sweep(store, fake, now=1000.0)
    assert summary["bench_fits"] == 1
    bf = [n for n in store.list_notifications() if n.kind == "bench_fit"]
    assert len(bf) == 1
    assert "Anna Berg" in bf[0].body and "Bo Java" not in bf[0].body   # bid/no-bid excludes the non-fit
    assert bf[0].jobs and bf[0].jobs[0]["title"] == "Senior Python Consultant"
    # idempotent: the same posting on a later sweep is already seen → no new bench_fit
    assert alerts.run_sweep(store, fake, now=2000.0)["bench_fits"] == 0


def test_sweep_no_bench_means_no_bench_fit():
    store, s, fake = _store_with_search()      # no consultants on the bench
    summary = alerts.run_sweep(store, fake, now=1000.0)
    assert summary["bench_fits"] == 0
    assert not [n for n in store.list_notifications() if n.kind == "bench_fit"]


def test_sweep_skips_search_with_missing_profile():
    store = MemoryStore()
    s = new_saved_search("No CV", {"cv_id": "gone", "keywords": "python", "sources": ["remotive"]})
    store.save_saved_search(s)
    summary = alerts.run_sweep(store, lambda *a: _Result([_Job("j1")]), now=1000.0)
    assert summary["searches_run"] == 0 and store.list_notifications() == []


def test_sweep_survives_a_failing_search():
    store, s, _ = _store_with_search()
    def boom(profile, settings_):
        raise RuntimeError("source down")
    summary = alerts.run_sweep(store, boom, now=1000.0)
    assert summary["searches_run"] == 0 and summary["new_matches"] == 0   # no crash


# --- sweep: reminders -----------------------------------------------------

def _applied_app(now, days_ago=8):
    a = Application(job_title="Backend Engineer", company="Acme", status="applied")
    a.applied_at = now - days_ago * _DAY
    a.created = now - (days_ago + 1) * _DAY
    return a


def test_sweep_raises_reminder_and_refreshes_not_duplicates():
    store = MemoryStore()
    store.save_application(_applied_app(now=10_000_000.0))
    summary = alerts.run_sweep(store, lambda *a: _Result([]), now=10_000_000.0)
    assert summary["reminders"] == 1
    reminders = [n for n in store.list_notifications() if n.kind == "reminder"]
    assert len(reminders) == 1 and "follow-up" in reminders[0].body.lower()

    # a later sweep must REFRESH the open reminder (same dedupe), not add a second one
    summary2 = alerts.run_sweep(store, lambda *a: _Result([]), now=10_000_000.0 + 2 * _DAY)
    assert summary2["reminders"] == 0
    assert len([n for n in store.list_notifications() if n.kind == "reminder"]) == 1


def test_sweep_reminder_read_then_qualifying_does_not_duplicate():
    # regression: a reminder the user READ (but didn't dismiss) must be refreshed in place on
    # the next sweep, NOT spawned as a brand-new duplicate (the unbounded-stream bug)
    store = MemoryStore()
    store.save_application(_applied_app(now=10_000_000.0))
    alerts.run_sweep(store, lambda *a: _Result([]), now=10_000_000.0)
    rem = [n for n in store.list_notifications() if n.kind == "reminder"]
    assert len(rem) == 1
    rem[0].read = True                                    # user reads it but keeps it
    store.save_notification(rem[0])

    alerts.run_sweep(store, lambda *a: _Result([]), now=10_000_000.0 + 1 * _DAY)
    rem2 = [n for n in store.list_notifications() if n.kind == "reminder"]
    assert len(rem2) == 1                                 # refreshed, not duplicated
    assert rem2[0].read is False                          # and re-surfaced as unread


def test_update_saved_search_atomic_and_missing():
    store, s, _ = _store_with_search()
    out = store.update_saved_search(s.id, lambda sv: setattr(sv, "new_count", 5))
    assert out is not None and out.new_count == 5
    assert store.get_saved_search(s.id).new_count == 5    # persisted
    assert store.update_saved_search("nope", lambda sv: None) is None


# --- prefs ----------------------------------------------------------------

@pytest.fixture
def tmp_prefs(tmp_path, monkeypatch):
    monkeypatch.setattr(alerts, "_FILE", tmp_path / "alerts.json")
    monkeypatch.delenv("JOBFINDER_ALERTS", raising=False)
    monkeypatch.delenv("JOBFINDER_ALERTS_INTERVAL_HOURS", raising=False)
    return tmp_path / "alerts.json"


def test_prefs_default_off_and_interval_clamped(tmp_prefs):
    assert alerts.get_prefs() == {"enabled": False, "interval_hours": 6}
    alerts.set_prefs(enabled=True, interval_hours=1)         # 1h is below the polite minimum
    p = alerts.get_prefs()
    assert p["enabled"] is True and p["interval_hours"] == 6
    alerts.set_prefs(interval_hours=24)
    assert alerts.get_prefs() == {"enabled": True, "interval_hours": 24}


def test_prefs_env_default(tmp_prefs, monkeypatch):
    monkeypatch.setenv("JOBFINDER_ALERTS", "1")
    assert alerts.get_prefs()["enabled"] is True            # env default with no file


# --- scheduler interval gating (no real thread) ---------------------------

def test_scheduler_maybe_run_respects_interval(tmp_prefs):
    alerts.set_prefs(enabled=True, interval_hours=6)
    store, s, fake = _store_with_search()
    sch = alerts.AlertScheduler(store, fake)
    sch._maybe_run(now=1000.0)
    assert sch.last_run == 1000.0                            # first run fires
    sch._maybe_run(now=1000.0 + 3600.0)                     # 1h later — within the 6h interval
    assert sch.last_run == 1000.0                            # not due, unchanged
    sch._maybe_run(now=1000.0 + 7 * 3600.0)                 # past the interval
    assert sch.last_run == 1000.0 + 7 * 3600.0              # ran again


def test_scheduler_disabled_does_nothing(tmp_prefs):
    alerts.set_prefs(enabled=False)
    sch = alerts.AlertScheduler(MemoryStore(), lambda *a: _Result([]))
    sch._maybe_run(now=1000.0)
    assert sch.last_run is None                              # disabled → no sweep


# --- API ------------------------------------------------------------------

def test_notifications_api_list_read_dismiss():
    client = TestClient(web.app)
    web.store.save_notification(Notification(kind="reminder", title="T", body="hi", created=1.0))
    d = client.get("/api/notifications").json()
    assert d["unread"] >= 1 and any(n["title"] == "T" for n in d["notifications"])
    nid = next(n["id"] for n in d["notifications"] if n["title"] == "T")
    assert client.post(f"/api/notifications/{nid}/read").status_code == 200
    assert client.get("/api/notifications").json()["notifications"][0]["read"] in (True, False)
    assert client.post("/api/notifications/read").json()["unread"] == 0
    assert client.delete(f"/api/notifications/{nid}").json()["ok"] is True


def test_alerts_config_api(tmp_prefs, monkeypatch):
    monkeypatch.setattr(web.alert_scheduler, "start", lambda: None)   # don't spawn the thread
    client = TestClient(web.app)
    assert client.get("/api/alerts/config").json()["enabled"] is False
    r = client.post("/api/alerts/config", json={"enabled": True, "interval_hours": 12}).json()
    assert r["enabled"] is True and r["interval_hours"] == 12


def test_alerts_run_now_api(monkeypatch):
    monkeypatch.setattr(web.alert_scheduler, "run_now",
                        lambda: {"searches_run": 0, "new_matches": 0, "reminders": 0, "ran_at": 1.0})
    assert TestClient(web.app).post("/api/alerts/run-now").json()["new_matches"] == 0


def test_export_and_delete_all_api():
    client = TestClient(web.app)
    web.store.save_notification(Notification(kind="reminder", title="ToWipe", created=2.0))
    bundle = client.get("/api/export").json()
    assert bundle["app"] == "Job Finder" and "data" in bundle
    assert "notifications" in bundle["data"] and "profiles" in bundle["data"]
    r = client.post("/api/data/delete-all").json()
    assert r["ok"] is True and "notifications" in r["deleted"]
    assert client.get("/api/notifications").json()["notifications"] == []   # wiped


def test_delete_all_runs_under_sweep_lock(monkeypatch):
    # regression: delete-all must hold the scheduler's sweep lock so an in-flight sweep can't
    # resurrect just-deleted rows
    held = {}
    real = web.store.delete_all
    def spy():
        held["locked"] = web.alert_scheduler._sweep_lock.locked()
        real()
    monkeypatch.setattr(web.store, "delete_all", spy)
    TestClient(web.app).post("/api/data/delete-all")
    assert held.get("locked") is True
