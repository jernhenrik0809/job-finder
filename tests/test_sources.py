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


# --- it-jobbank / HR-Manager / Jobicy / Careerjet -------------------------

from jobfinder.sources.itjobbank import ItJobbankSource
from jobfinder.sources.hrmanager import HRManagerSource, _msdate
from jobfinder.sources.jobicy import JobicySource
from jobfinder.sources.careerjet import CareerjetSource


def test_itjobbank_parses_rss():
    rss = (
        '<?xml version="1.0" encoding="ISO-8859-1"?><rss><channel>'
        '<item><title>Python Udvikler, Acme A/S</title><link>https://www.it-jobbank.dk/vis-job/h1</link>'
        '<pubDate>Mon, 16 Jun 2026 00:00:00 +0200</pubDate>'
        '<description>&lt;span class="jix_robotjob--area"&gt;København&lt;/span&gt; Build Python.&lt;/description&gt;</description></item>'
        '</channel></rss>'
    ).encode("iso-8859-1")
    with patch("jobfinder.sources.itjobbank.requests.get", return_value=_FakeRssResp(rss)):
        jobs = ItJobbankSource().search("python", limit=5)
    assert len(jobs) == 1
    assert jobs[0].title == "Python Udvikler" and jobs[0].company == "Acme A/S"
    assert jobs[0].location == "København" and jobs[0].source == "it-jobbank"


def test_hrmanager_parses_json_and_msdate():
    assert _msdate("/Date(1780396745000+0200)/") == "2026-06-02"
    assert _msdate(None) == "" and _msdate("nonsense") == ""
    payload = {"Items": [{
        "Name": "Jurist til Miljøstyrelsen",
        "Department": {"Name": "Miljøstyrelsen", "City": "Odense"},
        "WorkPlace": "Odense", "AdvertisementUrlSecure": "https://candidate.hr-manager.net/x",
        "Advertisements": [{"Content": "<p>Behandling af sager</p>"}],
        "Published": "/Date(1780396745000+0200)/",
    }]}
    # single alias, mocked
    src = HRManagerSource(aliases=("statensrekrutteringsloesning_tr",))
    with patch("jobfinder.sources.hrmanager.requests.get", return_value=_FakeResp(payload)):
        jobs = src.search("jurist", limit=5)
    assert len(jobs) == 1
    j = jobs[0]
    assert j.title == "Jurist til Miljøstyrelsen" and j.company == "Miljøstyrelsen"
    assert j.location == "Odense" and "Behandling" in j.description and j.posted == "2026-06-02"
    assert j.source == "HR-Manager (DK public sector)"


def test_hrmanager_survives_one_failing_alias():
    payload = {"Items": [{"Name": "Role", "Department": {"Name": "Co"}, "WorkPlace": "Aarhus",
                          "Advertisements": [{"Content": "x"}], "Published": "/Date(1780396745000)/"}]}
    calls = {"n": 0}
    def flaky(*a, **k):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("boom")          # first alias fails
        return _FakeResp(payload)
    src = HRManagerSource(aliases=("a", "b"))
    with patch("jobfinder.sources.hrmanager.requests.get", side_effect=flaky):
        jobs = src.search("role", limit=5)
    assert len(jobs) == 1                        # the second alias still produced a job


def test_jobicy_parses_json():
    payload = {"jobs": [{
        "jobTitle": "Backend Developer", "companyName": "Synthesia", "jobGeo": "Europe",
        "url": "https://jobicy.com/jobs/1", "jobDescription": "<p>Python</p>", "pubDate": "2026-06-16 10:00:00",
    }]}
    with patch("jobfinder.sources.jobicy.requests.get", return_value=_FakeResp(payload)):
        jobs = JobicySource().search("developer", limit=5)
    assert len(jobs) == 1
    assert jobs[0].title == "Backend Developer" and jobs[0].remote is True and jobs[0].posted == "2026-06-16"


def test_careerjet_requires_affid_and_parses():
    with pytest.raises(RuntimeError):
        CareerjetSource(affid=None).search("python")     # no affid → skipped with a clear error
    payload = {"jobs": [{
        "title": "Python Developer", "company": "DanskCo", "locations": "København",
        "url": "https://careerjet/1", "description": "<b>Django</b>", "date": "2026-06-15", "salary": "600000",
    }]}
    with patch("jobfinder.sources.careerjet.requests.get", return_value=_FakeResp(payload)):
        jobs = CareerjetSource(affid="aff123").search("python", limit=5)
    assert len(jobs) == 1
    j = jobs[0]
    assert j.title == "Python Developer" and j.location == "København" and j.source == "Careerjet"
    assert "Django" in j.description and j.salary == "600000"


# --- malformed-upstream robustness (review-found: one bad record must not drop the batch) ---

def test_hrmanager_survives_malformed_records_and_none_keywords():
    # a non-dict Item, plus records whose nested fields are the wrong type, must not crash or
    # discard the good record; and keywords=None must not crash on .lower()
    payload = {"Items": [
        "i-am-not-a-dict",                                   # non-dict element
        {"Name": "Bad dept", "Department": "Just a string",  # Department is a str, not a dict
         "Advertisements": ["raw string ad"],                # first ad is a str, not a dict
         "PositionLocation": "also a string", "Published": "/Date(1780396745000)/"},
        {"Name": "Good Role", "Department": {"Name": "Styrelsen", "City": "Odense"},
         "Advertisements": [{"Content": "<p>Sagsbehandling</p>"}], "Published": "/Date(1780396745000+0200)/"},
    ]}
    src = HRManagerSource(aliases=("statensrekrutteringsloesning_tr",))
    with patch("jobfinder.sources.hrmanager.requests.get", return_value=_FakeResp(payload)):
        jobs = src.search(keywords=None, location=None, limit=5)   # None must not crash
    titles = [j.title for j in jobs]
    assert "Good Role" in titles                             # the clean record survived
    assert "i-am-not-a-dict" not in titles
    good = next(j for j in jobs if j.title == "Good Role")
    assert good.company == "Styrelsen" and good.location == "Odense" and "Sagsbehandling" in good.description


def test_jobicy_skips_non_dict_and_coerces_nonstring_date():
    payload = {"jobs": [
        "not-a-dict",                                        # malformed entry — must be skipped
        {"jobTitle": "Dev", "companyName": "C", "jobGeo": "Denmark", "url": "u",
         "jobDescription": "<p>Python</p>", "pubDate": 1780396745},   # int date — must coerce, not crash
    ]}
    with patch("jobfinder.sources.jobicy.requests.get", return_value=_FakeResp(payload)):
        jobs = JobicySource().search("dev", limit=5)
    assert len(jobs) == 1 and jobs[0].title == "Dev"         # good record survived the bad one
    assert isinstance(jobs[0].posted, str)                   # int pubDate coerced, no TypeError


def test_careerjet_skips_non_dict_and_coerces_nonstring_date():
    payload = {"jobs": [
        12345,                                               # malformed entry — must be skipped
        {"title": "Python Dev", "company": "C", "locations": "København", "url": "u",
         "description": "<b>Django</b>", "date": 20260615, "salary": "x"},   # int date — must coerce
    ]}
    with patch("jobfinder.sources.careerjet.requests.get", return_value=_FakeResp(payload)):
        jobs = CareerjetSource(affid="aff123").search("python", limit=5)
    assert len(jobs) == 1 and jobs[0].title == "Python Dev"  # good record survived
    assert isinstance(jobs[0].posted, str)                   # int date coerced, no TypeError


# --- StepStone.dk / RemoteOK / We Work Remotely / Working Nomads / Freelancer.com ---------

from jobfinder.sources.stepstonedk import StepStoneDkSource
from jobfinder.sources.remoteok import RemoteOKSource
from jobfinder.sources.weworkremotely import WeWorkRemotelySource
from jobfinder.sources.workingnomads import WorkingNomadsSource
from jobfinder.sources.freelancer import FreelancerSource


def test_stepstonedk_parses_rss_and_description_fields():
    # location/company live in the HTML description (.job-location/.job-company), not a span.area
    desc = ('&lt;div class="result"&gt;&lt;div class="job-company"&gt;Trackman&lt;/div&gt;'
            '&lt;span class="job-location"&gt;Hørsholm&lt;/span&gt;'
            '&lt;div class="job-body"&gt;Build embedded Python services&lt;/div&gt;&lt;/div&gt;')
    rss = (
        '<?xml version="1.0" encoding="ISO-8859-1"?><rss><channel>'
        f'<item><title>Senior Python Developer, Trackman</title>'
        f'<link>https://www.stepstone.dk/vis-job/i1674365</link>'
        f'<pubDate>Mon, 15 Jun 2026 00:00:00 +0200</pubDate>'
        f'<description>{desc}</description></item>'
        '</channel></rss>'
    ).encode("iso-8859-1")
    with patch("jobfinder.sources.stepstonedk.requests.get", return_value=_FakeRssResp(rss)):
        jobs = StepStoneDkSource().search("python", limit=5)
    assert len(jobs) == 1
    j = jobs[0]
    assert j.title == "Senior Python Developer" and j.company == "Trackman"
    assert j.location == "Hørsholm" and "embedded Python" in j.description
    assert j.url == "https://www.stepstone.dk/vis-job/i1674365" and j.source == "StepStone.dk"
    assert j.posted == "2026-06-15"


def test_remoteok_skips_legal_head_and_maps():
    payload = [
        {"legal": "Please mention Remote OK", "last_updated": 123},     # element[0] metadata — skip
        {"id": "1", "position": "Senior Python Engineer", "company": "Acme",
         "location": "Remote", "url": "https://remoteok.com/jobs/1",
         "description": "<p>Build APIs</p>", "tags": ["python", "backend"],
         "date": "2026-06-16T04:08:17+00:00", "salary_min": 90000, "salary_max": 120000},
        {"id": "2", "position": "Sales Lead", "company": "Z", "tags": ["sales"],
         "description": "quota", "url": "u2", "epoch": 1781582897},
    ]
    with patch("jobfinder.sources.remoteok.requests.get", return_value=_FakeResp(payload)):
        jobs = RemoteOKSource().search("python", limit=5)
    assert len(jobs) == 1                                    # only the python job matched
    j = jobs[0]
    assert j.title == "Senior Python Engineer" and j.remote is True and j.posted == "2026-06-16"
    assert j.source == "Remote OK" and "120,000" in j.salary


def test_remoteok_skips_non_dict_elements():
    payload = [{"legal": "x"}, "not-a-dict", 42,
               {"id": "9", "position": "Dev", "company": "C", "url": "u", "description": "d", "tags": []}]
    with patch("jobfinder.sources.remoteok.requests.get", return_value=_FakeResp(payload)):
        jobs = RemoteOKSource().search("dev", limit=5)
    assert len(jobs) == 1 and jobs[0].title == "Dev"        # bad elements skipped, no crash


def test_weworkremotely_splits_company_role_on_first_colon():
    rss = (
        '<?xml version="1.0" encoding="UTF-8"?><rss><channel>'
        '<item><title>Knowmad Mood: Java/DevOps Senior</title>'
        '<region>Anywhere in the World</region>'
        '<link>https://weworkremotely.com/remote-jobs/x</link>'
        '<pubDate>Tue, 16 Jun 2026 20:31:47 +0000</pubDate>'
        '<description>&lt;p&gt;Build CI/CD pipelines&lt;/p&gt;</description></item>'
        '</channel></rss>'
    ).encode("utf-8")
    with patch("jobfinder.sources.weworkremotely.requests.get", return_value=_FakeRssResp(rss)):
        jobs = WeWorkRemotelySource().search("devops", limit=5)
    assert len(jobs) == 1
    j = jobs[0]
    assert j.company == "Knowmad Mood" and j.title == "Java/DevOps Senior"
    assert j.location == "Anywhere in the World" and j.remote is True and j.posted == "2026-06-16"
    assert j.source == "We Work Remotely"


def test_workingnomads_parses_array_and_skips_non_dict():
    payload = [
        "not-a-dict",
        {"url": "https://www.workingnomads.com/job/1", "title": "React Developer (Remote)",
         "description": "<p>React + Node</p>", "company_name": "TELUS", "category_name": "Development",
         "tags": "react,nodejs,english", "location": "Europe only", "pub_date": "2026-06-11T11:06:58-04:00"},
    ]
    with patch("jobfinder.sources.workingnomads.requests.get", return_value=_FakeResp(payload)):
        jobs = WorkingNomadsSource().search("react", limit=5)
    assert len(jobs) == 1
    j = jobs[0]
    assert j.title == "React Developer (Remote)" and j.company == "TELUS"
    assert j.location == "Europe only" and j.remote is True and j.posted == "2026-06-11"
    assert j.source == "Working Nomads"


def test_freelancer_requires_token_and_parses():
    with pytest.raises(RuntimeError):
        FreelancerSource(token=None).search("python")        # no token → skipped with a clear error
    payload = {"status": "success", "result": {"projects": [
        "not-a-dict",
        {"title": "Build a Django API", "seo_url": "web/build-a-django-api",
         "description": "Need a REST API", "jobs": [{"name": "Python"}, {"name": "Django"}],
         "submitdate": 1781678580, "budget": {"minimum": 250, "maximum": 750},
         "currency": {"code": "USD"}},
    ], "total_count": 1}}
    with patch("jobfinder.sources.freelancer.requests.get", return_value=_FakeResp(payload)):
        jobs = FreelancerSource(token="tok123").search("python", limit=5)
    assert len(jobs) == 1                                    # non-dict project skipped
    j = jobs[0]
    assert j.title == "Build a Django API" and j.remote is True and j.company == ""
    assert j.url == "https://www.freelancer.com/projects/web/build-a-django-api"
    assert "Django" in j.description and "USD" in j.salary and j.posted == "2026-06-17"
    assert j.source == "Freelancer"


# --- ATS (Greenhouse / Lever / Ashby) ------------------------------------

from jobfinder.sources.ats import ATSSource


def _ats_get(payloads):
    def _get(url, *a, **k):
        if "greenhouse.io" in url:
            return _FakeResp(payloads.get("greenhouse", {"jobs": []}))
        if "lever.co" in url:
            return _FakeResp(payloads.get("lever", []))
        if "ashbyhq.com" in url:
            return _FakeResp(payloads.get("ashby", {"jobs": []}))
        return _FakeResp({})
    return _get


def test_ats_greenhouse_unescapes_entity_encoded_content():
    payload = {"jobs": [{
        "title": "Account Executive Denmark", "location": {"name": "Copenhagen"},
        "absolute_url": "https://corporate.trustpilot.com/careers/job/1",
        "content": "&lt;p&gt;Build &amp; grow&lt;/p&gt;", "updated_at": "2026-06-16T15:48:40-04:00",
        "company_name": "Trustpilot",
    }]}
    with patch("jobfinder.sources.ats.requests.get", side_effect=_ats_get({"greenhouse": payload})):
        jobs = ATSSource(boards=[("greenhouse", "trustpilot")]).search("denmark", limit=5)
    assert len(jobs) == 1
    j = jobs[0]
    assert j.title == "Account Executive Denmark" and j.company == "Trustpilot"
    assert j.location == "Copenhagen" and j.posted == "2026-06-16" and j.source == "ATS (Greenhouse)"
    assert "Build & grow" in j.description and "<" not in j.description   # entity-decoded, tags stripped


def test_ats_lever_epoch_ms_and_remote():
    payload = [{
        "text": "Android Engineer", "categories": {"location": "Copenhagen"},
        "hostedUrl": "https://jobs.lever.co/veo/1", "workplaceType": "remote",
        "descriptionPlain": "Build Android apps", "createdAt": 1779435981707,   # epoch MS
    }]
    with patch("jobfinder.sources.ats.requests.get", side_effect=_ats_get({"lever": payload})):
        jobs = ATSSource(boards=[("lever", "veo")]).search("android", limit=5)
    assert len(jobs) == 1
    j = jobs[0]
    assert j.title == "Android Engineer" and j.company == "Veo" and j.location == "Copenhagen"
    assert j.remote is True and j.posted == "2026-05-22" and j.source == "ATS (Lever)"


def test_ats_ashby_skips_unlisted():
    payload = {"jobs": [
        {"title": "Hidden", "isListed": False, "location": "X", "jobUrl": "u",
         "descriptionPlain": "x", "publishedAt": "2026-01-01T00:00:00.000+00:00"},
        {"title": "ML Engineer", "isListed": True, "location": "Copenhagen, Denmark",
         "jobUrl": "https://jobs.ashbyhq.com/Corti/2", "descriptionPlain": "Build ML",
         "publishedAt": "2026-04-07T17:12:35.753+00:00", "isRemote": True},
    ]}
    with patch("jobfinder.sources.ats.requests.get", side_effect=_ats_get({"ashby": payload})):
        jobs = ATSSource(boards=[("ashby", "Corti")]).search("", limit=5)
    assert len(jobs) == 1 and jobs[0].title == "ML Engineer"          # unlisted skipped
    assert jobs[0].posted == "2026-04-07" and jobs[0].remote is True and jobs[0].source == "ATS (Ashby)"


def test_ats_survives_a_failing_board():
    def _get(url, *a, **k):
        if "greenhouse" in url:
            raise RuntimeError("boom")
        return _FakeResp([{"text": "Dev", "categories": {"location": "Aarhus"},
                           "hostedUrl": "u", "descriptionPlain": "go", "createdAt": 1779435981707}])
    with patch("jobfinder.sources.ats.requests.get", side_effect=_get):
        jobs = ATSSource(boards=[("greenhouse", "x"), ("lever", "y")]).search("dev", limit=5)
    assert len(jobs) == 1 and jobs[0].title == "Dev"                  # lever survived greenhouse failing


def test_ats_empty_board_list_returns_empty_not_error():
    # a fully-misconfigured JOBFINDER_ATS_COMPANIES (no valid boards) must yield [], not a
    # misleading "all boards unavailable" RuntimeError — and must make no request
    called = {"n": 0}
    def _get(*a, **k):
        called["n"] += 1
        return _FakeResp({})
    with patch("jobfinder.sources.ats.requests.get", side_effect=_get):
        assert ATSSource(boards=[]).search("python", limit=5) == []
    assert called["n"] == 0


def test_freelancer_tolerates_string_and_junk_budget():
    # a budget serialised as strings (or junk) must NOT crash the :g salary format and drop the batch
    payload = {"result": {"projects": [
        {"title": "String budget", "seo_url": "a", "description": "x",
         "budget": {"minimum": "100", "maximum": "200"}, "currency": {"code": "USD"}, "submitdate": 1781678580},
        {"title": "Junk budget", "seo_url": "b", "description": "y",
         "budget": "not-a-dict", "submitdate": 1781678580},
        {"title": "No budget", "seo_url": "c", "description": "z", "submitdate": 1781678580},
    ]}}
    with patch("jobfinder.sources.freelancer.requests.get", return_value=_FakeResp(payload)):
        jobs = FreelancerSource(token="t").search("dev", limit=5)
    assert [j.title for j in jobs] == ["String budget", "Junk budget", "No budget"]   # none dropped
    assert "100" in jobs[0].salary and "USD" in jobs[0].salary
    assert jobs[1].salary == "" and jobs[2].salary == ""                              # no crash
