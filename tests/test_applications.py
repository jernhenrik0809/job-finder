"""Tests for the Application lifecycle state machine."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jobfinder.applications import (
    STATUSES, new_application, set_status, attach_letter, job_snapshot, record_event,
)

JOB = {
    "title": "AI Ethics Researcher", "company": "Anthropic", "url": "https://x/1",
    "source": "LinkedIn", "score": 71, "location": "Remote",
    "description": "Research AI safety.", "matched_skills": ["python"], "missing_skills": ["rl"],
}


def test_new_application_snapshots_job_and_logs_event():
    a = new_application(JOB, cv_id="cv1")
    assert a.status == "saved" and a.cv_id == "cv1"
    assert a.job_title == "AI Ethics Researcher" and a.company == "Anthropic"
    assert a.job["matched_skills"] == ["python"] and a.job["description"]
    assert a.events and a.events[0]["type"] == "created"
    assert a.created > 0 and a.id


def test_set_status_validates_and_logs_and_stamps_applied():
    a = new_application(JOB)
    set_status(a, "ready")
    assert a.status == "ready"
    assert a.events[-1]["type"] == "status" and "ready" in a.events[-1]["detail"]
    assert a.applied_at is None
    set_status(a, "applied")
    assert a.applied_at is not None
    first_applied = a.applied_at
    # moving away and back must not reset applied_at
    set_status(a, "interview")
    set_status(a, "applied")
    assert a.applied_at == first_applied


def test_set_status_rejects_unknown():
    a = new_application(JOB)
    with pytest.raises(ValueError):
        set_status(a, "promoted")           # not a real status
    assert a.status == "saved"


def test_set_status_noop_same_status_logs_nothing():
    a = new_application(JOB)
    n = len(a.events)
    set_status(a, "saved")
    assert len(a.events) == n


def test_attach_letter_moves_saved_to_ready():
    a = new_application(JOB)
    attach_letter(a, "Application for X", "Dear team...", "template")
    assert a.status == "ready" and a.generator == "template"
    assert a.body == "Dear team..." and a.subject == "Application for X"
    # but attaching to an already-applied application does NOT regress its status
    set_status(a, "applied")
    attach_letter(a, "v2", "Dear team v2...", "llm")
    assert a.status == "applied" and a.body == "Dear team v2..."


def test_job_snapshot_reconstructs_for_regeneration():
    a = new_application(JOB)
    j = job_snapshot(a)
    assert j["title"] == "AI Ethics Researcher" and j["company"] == "Anthropic"
    assert j["description"] and j["matched_skills"] == ["python"]


def test_all_statuses_are_distinct():
    assert len(STATUSES) == len(set(STATUSES))
