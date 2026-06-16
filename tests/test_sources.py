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


def test_jooble_handles_numeric_salary():
    # Jooble's salary is usually a string but can come back numeric; must not crash the source.
    payload = {"jobs": [{
        "title": "Data Engineer", "company": "NumCo", "location": "Odense",
        "link": "https://jooble/2", "snippet": "Python", "updated": "2026-06-09",
        "salary": 45000,                                          # int, not str
    }]}
    with patch("jobfinder.sources.jooble.requests.post", return_value=_FakeResp(payload)):
        jobs = JoobleSource(api_key="k").search("python", limit=5)
    assert len(jobs) == 1                                         # whole source not wiped out
    assert jobs[0].salary == "45000"                             # coerced, no AttributeError


def test_adzuna_handles_decimal_string_salary():
    # A proxy/cache could serialize salary as a decimal string; int(float()) must absorb it.
    payload = {"results": [{
        "title": "ML Engineer", "company": {"display_name": "Acme DK"},
        "location": {"display_name": "København"}, "redirect_url": "https://adzuna/2",
        "description": "Python", "created": "2026-06-10",
        "salary_min": "500000.0", "salary_max": "700000.0",      # decimal strings
    }]}
    with patch("jobfinder.sources.adzuna.requests.get", return_value=_FakeResp(payload)):
        jobs = AdzunaSource(app_id="id", app_key="key").search("python", limit=5)
    assert len(jobs) == 1                                         # no ValueError → source survives
    assert jobs[0].salary == "500,000–700,000"


# --- new Denmark sources: The Hub / The Muse / Jobindex --------------------

from jobfinder.sources.thehub import TheHubSource
from jobfinder.sources.themuse import TheMuseSource
from jobfinder.sources.jobindex import JobindexSource


def test_thehub_parses_dk_jobs_and_stops_at_last_page():
    payload = {"docs": [{
        "title": "Backend Engineer", "company": {"name": "Acme DK"},
        "location": {"address": "Copenhagen, Denmark"}, "absoluteJobUrl": "https://thehub.io/jobs/abc",
        "description": "<p>Python and Django backend</p>", "publishedAt": "2026-06-10T09:00:00.000Z",
        "isRemote": False,
    }], "pages": 1, "total": 1}
    with patch("jobfinder.sources.thehub.requests.get", return_value=_FakeResp(payload)):
        jobs = TheHubSource().search("backend", limit=5)
    assert len(jobs) == 1
    j = jobs[0]
    assert j.title == "Backend Engineer" and j.company == "Acme DK" and j.source == "The Hub"
    assert j.location == "Copenhagen, Denmark" and j.url == "https://thehub.io/jobs/abc"
    assert j.posted == "2026-06-10" and "Python" in j.description


def test_thehub_keyword_filter_drops_non_matches():
    payload = {"docs": [
        {"title": "Marketing Manager", "company": {"name": "X"}, "location": {"address": "Copenhagen"},
         "absoluteJobUrl": "u", "description": "brand campaigns", "publishedAt": "2026-06-01", "isRemote": False},
    ], "pages": 1}
    with patch("jobfinder.sources.thehub.requests.get", return_value=_FakeResp(payload)):
        assert TheHubSource().search("python developer", limit=5) == []


def test_themuse_keeps_only_denmark_located():
    payload = {"results": [
        {"name": "DK Role", "company": {"name": "Celonis"}, "locations": [{"name": "Copenhagen, Denmark"}],
         "refs": {"landing_page": "https://themuse/1"}, "contents": "Python", "publication_date": "2026-06-02T10:00:00Z"},
        {"name": "US Role", "company": {"name": "Optum"}, "locations": [{"name": "Flexible / Remote"}],
         "refs": {"landing_page": "https://themuse/2"}, "contents": "Python", "publication_date": "2026-06-02T10:00:00Z"},
    ], "page_count": 1}
    with patch("jobfinder.sources.themuse.requests.get", return_value=_FakeResp(payload)):
        jobs = TheMuseSource().search("python", limit=5)
    assert len(jobs) == 1                                   # the OR-global filter is enforced client-side
    assert jobs[0].title == "DK Role" and jobs[0].location == "Copenhagen, Denmark" and jobs[0].source == "The Muse"


class _FakeRssResp:
    def __init__(self, content: bytes):
        self.content = content
    def raise_for_status(self):
        pass


def test_jobindex_parses_rss_iso8859_and_splits_title():
    # ISO-8859-1 feed with a Danish place name (ø) to confirm correct decoding
    rss = (
        '<?xml version="1.0" encoding="ISO-8859-1"?>'
        '<rss version="2.0"><channel>'
        '<item>'
        '<title>Senior Python Udvikler, NTI A/S</title>'
        '<link>https://www.jobindex.dk/vis-job/h123</link>'
        '<pubDate>Tue, 16 Jun 2026 00:00:00 +0200</pubDate>'
        '<description>&lt;div&gt;&lt;span class="jix_robotjob--area"&gt;Værløse&lt;/span&gt; Build Python services&lt;/div&gt;</description>'
        '</item>'
        '</channel></rss>'
    ).encode("iso-8859-1")
    with patch("jobfinder.sources.jobindex.requests.get", return_value=_FakeRssResp(rss)):
        jobs = JobindexSource().search("python", limit=5)
    assert len(jobs) == 1
    j = jobs[0]
    assert j.title == "Senior Python Udvikler" and j.company == "NTI A/S"   # split on last comma
    assert j.location == "Værløse"                                 # ISO-8859-1 decoded to unicode
    assert j.url == "https://www.jobindex.dk/vis-job/h123" and j.posted == "2026-06-16"
    assert j.source == "Jobindex" and "Python" in j.description


def test_jobindex_location_filter():
    rss = (
        '<?xml version="1.0" encoding="ISO-8859-1"?><rss><channel>'
        '<item><title>Dev, Co</title><link>u</link><pubDate>Tue, 16 Jun 2026 00:00:00 +0200</pubDate>'
        '<description>&lt;span class="jix_robotjob--area"&gt;Aarhus&lt;/span&gt;</description></item>'
        '</channel></rss>'
    ).encode("iso-8859-1")
    with patch("jobfinder.sources.jobindex.requests.get", return_value=_FakeRssResp(rss)):
        assert JobindexSource().search("dev", location="Copenhagen", limit=5) == []   # Aarhus != Copenhagen


def test_themuse_tolerates_malformed_location_entries():
    # a null / non-dict locations entry must NOT discard the whole result set
    payload = {"results": [
        {"name": "Good DK", "company": {"name": "C"}, "locations": [None, "Copenhagen", {"name": "Aarhus, Denmark"}],
         "refs": {"landing_page": "u"}, "contents": "Python", "publication_date": "2026-06-02"},
    ], "page_count": 1}
    with patch("jobfinder.sources.themuse.requests.get", return_value=_FakeResp(payload)):
        jobs = TheMuseSource().search("python", limit=5)
    assert len(jobs) == 1 and jobs[0].location == "Aarhus, Denmark"   # survived the bad entries


def test_thehub_tolerates_non_string_description():
    payload = {"docs": [{
        "title": "Dev", "company": {"name": "C"}, "location": {"address": "Copenhagen"},
        "absoluteJobUrl": "u", "description": 12345, "publishedAt": "2026-06-01", "isRemote": False,
    }], "pages": 1}
    with patch("jobfinder.sources.thehub.requests.get", return_value=_FakeResp(payload)):
        jobs = TheHubSource().search("dev", limit=5)
    assert len(jobs) == 1 and jobs[0].description == "12345"          # coerced, no TypeError
