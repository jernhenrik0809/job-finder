"""Tests for pipeline analytics (funnel, response rate, time-to-response, nudges)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jobfinder.applications import Application
from jobfinder.insights import compute_insights

NOW = 1_000_000.0
DAY = 86400.0


def d(n):  # n days ago
    return NOW - n * DAY


def _app(aid, status, *, applied_at=None, body="", generator="", source="", created=None, events=None):
    return Application(job_title="Role " + aid, company="C", job_source=source, status=status,
                       applied_at=applied_at, body=body, generator=generator,
                       created=created if created is not None else d(1), updated=created if created is not None else d(1),
                       id=aid, events=events or [{"ts": d(40), "type": "created", "detail": "created"}])


def _apps():
    return [
        _app("A", "saved"),                                                   # saved only
        _app("B", "ready", body="letter", generator="template", created=d(5)),  # drafted, not applied (stale 5d)
        _app("C", "applied", applied_at=d(10), body="letter", generator="template", source="LinkedIn",
             events=[{"ts": d(11), "type": "created"}, {"ts": d(10), "type": "status", "detail": "saved → applied"}]),
        _app("D", "interview", applied_at=d(20), body="letter", generator="llm", source="Remotive",
             events=[{"ts": d(21), "type": "created"},
                     {"ts": d(20), "type": "status", "detail": "ready → applied"},
                     {"ts": d(18), "type": "status", "detail": "applied → screening"},
                     {"ts": d(17), "type": "status", "detail": "screening → interview"}]),
        _app("E", "offer", applied_at=d(30), body="letter", generator="llm", source="LinkedIn",
             events=[{"ts": d(31), "type": "created"},
                     {"ts": d(30), "type": "status", "detail": "ready → applied"},
                     {"ts": d(25), "type": "status", "detail": "applied → offer"}]),
    ]


def test_funnel_counts():
    r = compute_insights(_apps(), now=NOW)
    funnel = {f["stage"]: f["count"] for f in r["funnel"]}
    assert funnel == {"saved": 5, "drafted": 4, "applied": 3, "interviewing": 2, "offer": 1}


def test_response_rate_and_offers():
    r = compute_insights(_apps(), now=NOW)
    assert r["response_rate"] == 67          # 2 responded / 3 applied
    assert r["offers"] == 1


def test_avg_time_to_response():
    r = compute_insights(_apps(), now=NOW)
    # D: screening 18d after applied@20d → 2d ; E: offer 25d after applied@30d → 5d ; mean = 3.5
    assert r["avg_time_to_response_days"] == 3.5


def test_by_source_applied():
    r = compute_insights(_apps(), now=NOW)
    by = {x["source"]: x["applied"] for x in r["by_source"]}
    assert by == {"LinkedIn": 2, "Remotive": 1}


def test_nudges_stale_applied_and_ready():
    r = compute_insights(_apps(), now=NOW)
    ids = [n["id"] for n in r["nudges"]]
    assert ids == ["C", "B"]                 # C applied 10d (stale), B ready 5d; sorted by age desc
    assert "follow-up" in r["nudges"][0]["message"].lower()


def test_empty_pipeline_is_safe():
    r = compute_insights([], now=NOW)
    assert r["total"] == 0 and r["response_rate"] == 0 and r["nudges"] == []
    assert r["avg_time_to_response_days"] is None
    assert {f["stage"] for f in r["funnel"]} == {"saved", "drafted", "applied", "interviewing", "offer"}


def test_over_time_has_eight_weekly_buckets():
    r = compute_insights(_apps(), now=NOW)
    assert len(r["over_time"]) == 8 and r["over_time"][-1]["label"] == "now"
