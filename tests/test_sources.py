"""Regression tests for source parsing robustness (no real network).

These guard the None-handling fixes: external job APIs can return a present-but-null
field, and dict.get(k, default) does NOT substitute the default for an explicit None.
"""
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jobfinder.sources.remotive import RemotiveSource
from jobfinder.sources.jsearch import JSearchSource
from jobfinder.sources.adzuna import AdzunaSource
from jobfinder.sources.jooble import JoobleSource


class _FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def test_remotive_handles_null_fields():
    payload = {"jobs": [{
        "title": None, "company_name": None, "candidate_required_location": None,
        "url": None, "description": None, "publication_date": None, "salary": None,
    }]}
    with patch("jobfinder.sources.remotive.requests.get", return_value=_FakeResp(payload)):
        jobs = RemotiveSource().search("python", limit=5)
    assert len(jobs) == 1
    j = jobs[0]
    assert j.title == "" and j.company == ""
    assert j.posted == "" and j.location == "Remote"  # no crash on None slice/strip


def test_jsearch_handles_null_title():
    payload = {"data": [{
        "job_title": None, "employer_name": None, "job_city": None, "job_country": None,
        "job_description": None, "job_apply_link": "https://example.com/job/1",
    }]}
    with patch("jobfinder.sources.jsearch.requests.get", return_value=_FakeResp(payload)):
        jobs = JSearchSource(api_key="dummy").search("python", limit=5)
    assert len(jobs) == 1
    assert jobs[0].title == ""  # no AttributeError on None.strip()
    assert jobs[0].url == "https://example.com/job/1"


def test_adzuna_requires_keys_and_parses_denmark_results():
    with pytest.raises(RuntimeError):
        AdzunaSource(app_id=None, app_key=None).search("python")   # no key → clear error, skipped
    payload = {"results": [{
        "title": "Backend Developer", "company": {"display_name": "Acme DK"},
        "location": {"display_name": "København, Denmark"}, "redirect_url": "https://adzuna/1",
        "description": "<p>Python, Django and AWS</p>", "created": "2026-06-10T09:00:00Z",
        "salary_min": 500000, "salary_max": 700000,
    }]}
    with patch("jobfinder.sources.adzuna.requests.get", return_value=_FakeResp(payload)):
        jobs = AdzunaSource(app_id="id", app_key="key", country="dk").search("python", location="København", limit=5)
    assert len(jobs) == 1
    j = jobs[0]
    assert j.title == "Backend Developer" and j.company == "Acme DK" and j.source == "Adzuna"
    assert "Python" in j.description and j.salary and j.url == "https://adzuna/1"
    assert j.posted == "2026-06-10"


def test_jooble_requires_key_and_parses():
    with pytest.raises(RuntimeError):
        JoobleSource(api_key=None).search("python")
    payload = {"jobs": [{
        "title": "Python Udvikler", "company": "DanskCo", "location": "Aarhus, Denmark",
        "link": "https://jooble/1", "snippet": "<b>Django</b> and Python", "updated": "2026-06-09T12:00:00.000",
        "salary": "45000 DKK",
    }]}
    with patch("jobfinder.sources.jooble.requests.post", return_value=_FakeResp(payload)):
        jobs = JoobleSource(api_key="k").search("python", location="Denmark", limit=5)
    assert len(jobs) == 1
    assert jobs[0].title == "Python Udvikler" and jobs[0].source == "Jooble"
    assert jobs[0].url == "https://jooble/1" and "Django" in jobs[0].description


def test_jooble_defaults_to_denmark_location():
    captured = {}

    class _Resp(_FakeResp):
        pass

    def _fake_post(url, json=None, headers=None, timeout=None):
        captured["body"] = json
        return _FakeResp({"jobs": []})

    with patch("jobfinder.sources.jooble.requests.post", side_effect=_fake_post):
        JoobleSource(api_key="k").search("python")               # no location given
    assert captured["body"]["location"] == "Denmark"             # stays Denmark-relevant
