"""Regression tests for source parsing robustness (no real network).

These guard the None-handling fixes: external job APIs can return a present-but-null
field, and dict.get(k, default) does NOT substitute the default for an explicit None.
"""
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jobfinder.sources.remotive import RemotiveSource
from jobfinder.sources.jsearch import JSearchSource


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
