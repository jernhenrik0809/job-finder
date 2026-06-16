"""Unit tests for the core job-finder logic (no network required)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jobfinder.skills import extract_skills, skill_overlap
from jobfinder.cv_parser import CVProfile, build_profile, extract_text, looks_empty
from jobfinder.matcher import rank_jobs, MatchConfig
from jobfinder.sources.base import Job

SAMPLE = Path(__file__).parent / "sample_cv.txt"


# --- skills ---------------------------------------------------------------

def test_extract_skills_finds_known_skills():
    text = "Experienced in Python, Django and AWS with some Kubernetes."
    skills = extract_skills(text)
    assert "python" in skills
    assert "django" in skills
    assert "aws" in skills
    assert "kubernetes" in skills


def test_extract_skills_no_substring_false_positives():
    # "Go" and "R" and "C" should not be matched from unrelated words.
    text = "I really care about great products and growth."
    skills = extract_skills(text)
    assert "go" not in skills
    assert "r" not in skills
    assert "c" not in skills


def test_extract_skills_no_copyright_false_positive():
    # "(c)" copyright text and standalone bullet letters must not match the C/R language.
    text = "Copyright (c) 2026 Acme Inc. All rights reserved. Option (r) selected."
    skills = extract_skills(text)
    assert "c" not in skills
    assert "r" not in skills
    # but a real list mention is still detected
    assert "c" in extract_skills("Languages: C, Python, Java")


def test_extract_skills_matches_special_chars():
    text = "Strong C++ and C# developer with .NET and Node.js experience."
    skills = extract_skills(text)
    assert "c++" in skills
    assert "c#" in skills
    assert ".net" in skills
    assert "node.js" in skills


def test_skill_overlap():
    matched, missing = skill_overlap(["python", "aws"], ["python", "go", "aws", "docker"])
    assert set(matched) == {"python", "aws"}
    assert set(missing) == {"go", "docker"}


# --- cv parsing -----------------------------------------------------------

def test_build_profile_from_sample():
    text = extract_text(SAMPLE)
    profile = build_profile(text)
    assert "python" in profile.skills
    assert "go" in profile.skills
    assert profile.years_experience and profile.years_experience >= 5
    assert profile.seniority == "senior"
    assert any("engineer" in t for t in profile.titles)
    assert profile.suggested_keywords


def test_location_not_detected_from_skill_line():
    # "Skills: Python, Django" must not be read as a "City, Region" location
    p = build_profile("Jordan Smith\nBackend Developer\nSkills: Python, Django, FastAPI, AWS")
    assert p.location is None


def test_location_detected_from_contact_line():
    p = build_profile("Jane Doe\nSan Francisco, CA\nSoftware Engineer")
    assert p.location == "San Francisco, CA"


def test_looks_empty():
    assert looks_empty("") is True
    assert looks_empty("   \n  ") is True
    assert looks_empty("a real cv with plenty of actual words " * 5) is False


# --- matching -------------------------------------------------------------

def _profile():
    return build_profile(extract_text(SAMPLE))


def test_rank_jobs_orders_by_relevance():
    profile = _profile()
    jobs = [
        Job(title="Senior Python Engineer",
            company="GoodFit",
            description="We need Python, Django, AWS, Kubernetes, microservices and REST API design.",
            source="test"),
        Job(title="Marketing Manager",
            company="BadFit",
            description="Lead social media marketing, SEO, content marketing and brand campaigns.",
            source="test"),
        Job(title="Backend Engineer",
            company="OkFit",
            description="Go and Python backend with PostgreSQL and Docker on AWS.",
            source="test"),
    ]
    ranked = rank_jobs(profile, jobs, MatchConfig(semantic=False))
    assert ranked[0].company in ("GoodFit", "OkFit")
    assert ranked[-1].company == "BadFit"
    # the python role should beat the marketing role decisively
    good = next(j for j in ranked if j.company == "GoodFit")
    bad = next(j for j in ranked if j.company == "BadFit")
    assert good.score > bad.score
    assert "python" in [s.lower() for s in good.matched_skills]


def test_rank_jobs_populates_explainability():
    profile = _profile()
    jobs = [Job(title="Data Engineer", company="X",
                description="Python, Spark, Airflow, Kafka and some Rust required.",
                source="test")]
    rank_jobs(profile, jobs)
    job = jobs[0]
    assert 0 <= job.score <= 100
    assert "python" in [s.lower() for s in job.matched_skills]
    assert "rust" in [s.lower() for s in job.missing_skills]


def test_rank_jobs_empty_list():
    assert rank_jobs(_profile(), []) == []


# --- explanation object ("why this score?") -------------------------------

def test_explanation_components_sum_to_score():
    profile = _profile()
    jobs = [Job(title="Senior Python Engineer", company="X",
                description="Python, Django, AWS, Docker and PostgreSQL for backend APIs.",
                source="test")]
    rank_jobs(profile, jobs)
    ex = jobs[0].explanation
    assert ex and ex["components"]
    # the per-component points are an honest decomposition: they sum to the score
    total = round(sum(c["points"] for c in ex["components"]), 1)
    assert abs(total - jobs[0].score) < 0.2
    # and each component's ceiling caps its contribution
    for c in ex["components"]:
        assert 0 <= c["points"] <= c["max_points"] + 1e-9
        assert 0 <= c["strength"] <= 100


def test_explanation_skips_skills_when_posting_has_none():
    profile = _profile()
    # a posting with no recognisable tech skills — skill overlap is unknown, not zero
    jobs = [Job(title="Office Coordinator", company="Y",
                description="Greet visitors, manage calendars and order supplies.",
                source="test")]
    rank_jobs(profile, jobs)
    ex = jobs[0].explanation
    assert ex["skills_detected"] is False
    keys = [c["key"] for c in ex["components"]]
    assert "skills" not in keys            # omitted, not scored as 0
    # remaining components re-normalise so their ceilings still sum to 100
    assert abs(sum(c["max_points"] for c in ex["components"]) - 100) < 0.2


def test_explanation_reasons_mention_matched_skills():
    profile = _profile()
    jobs = [Job(title="Backend Engineer", company="Z",
                description="Strong Python, Django and AWS experience required.",
                source="test")]
    rank_jobs(profile, jobs)
    reasons = " ".join(jobs[0].explanation["reasons"]).lower()
    assert "skill" in reasons and any(s in reasons for s in ("python", "django", "aws"))


def test_explanation_survives_json_round_trip():
    profile = _profile()
    jobs = [Job(title="Python Developer", company="W",
                description="Python and Docker.", source="test")]
    rank_jobs(profile, jobs)
    import json
    d = jobs[0].to_dict()
    again = json.loads(json.dumps(d))         # the API serialises Job via to_dict
    assert again["explanation"]["components"]


# --- ranking nudges (bounded, never-penalizing, explainable) ---------------

from datetime import date
from jobfinder.matcher import MatchConfig, NUDGE_CAP

_TODAY = date(2026, 6, 16)


def _senior_profile():
    return CVProfile(raw_text="Senior Python developer. Django, FastAPI, AWS, Docker, PostgreSQL.",
                     skills=["python", "django", "fastapi", "aws", "docker", "postgresql"],
                     titles=["Python Developer"], seniority="senior", location="Copenhagen")


def _job(**kw):
    return Job(title=kw.get("title", "Python Developer"), company="X",
               description=kw.get("desc", "Python Django AWS backend role."),
               source=kw.get("source", "test"), posted=kw.get("posted", ""),
               location=kw.get("loc", ""), remote=kw.get("remote", False), salary=kw.get("salary", ""))


def _score(job, **cfg):
    jobs = [job]
    rank_jobs(_senior_profile(), jobs, MatchConfig(today=_TODAY, **cfg))
    return jobs[0]


def test_nudges_never_penalize():
    # a job with NO nudge signal scores its base; with signals it can only go up
    plain = _score(_job())
    boosted = _score(_job(title="Senior Python Developer", posted="2026-06-15",
                          loc="Copenhagen, Denmark", source="Arbeitnow", remote=True),
                     search_location="Copenhagen", search_remote=True)
    assert plain.explanation["nudge_points"] == 0.0
    assert boosted.score >= boosted.explanation["score"] - boosted.explanation["nudge_points"]  # base ≤ score
    assert boosted.explanation["nudge_points"] > 0


def test_nudge_points_keep_components_summing_to_score():
    j = _score(_job(title="Senior Python Developer", posted="2026-06-14", source="Arbeitnow"))
    ex = j.explanation
    assert any(c.get("bonus") for c in ex["components"])
    assert abs(sum(c["points"] for c in ex["components"]) - j.score) < 0.2


def test_no_nudge_means_no_bonus_component():
    ex = _score(_job()).explanation       # posted='', no location/seniority/remote signal
    assert ex["nudge_points"] == 0.0
    assert all(not c.get("bonus") for c in ex["components"])
    assert "nudges" not in [c["key"] for c in ex["components"]]


def test_recency_bands_and_safe_parsing():
    assert _score(_job(posted="2026-06-15")).explanation["nudge_points"] == 1.5     # fresh (≤7d)
    assert _score(_job(posted="2026-05-30")).explanation["nudge_points"] == 0.7     # recent (≤30d)
    assert _score(_job(posted="2026-01-01")).explanation["nudge_points"] == 0.0     # stale
    assert _score(_job(posted="2026-06-20")).explanation["nudge_points"] == 1.5     # future → freshest
    for bad in ("", "not-a-date", "2026-13-99"):
        assert _score(_job(posted=bad)).explanation["nudge_points"] == 0.0          # safe, no crash
    # a full ISO datetime is sliced to the date and still parses
    assert _score(_job(posted="2026-06-12T08:00:00.000Z")).explanation["nudge_points"] == 1.5


def test_remote_nudge_trusts_only_real_remote_sources():
    for src in ("Arbeitnow", "JSearch/Google"):
        assert _score(_job(source=src, remote=True), search_remote=True).explanation["nudge_points"] == 0.5
    for src in ("Adzuna", "Jooble", "Remotive"):   # these echo/hardcode remote → not trusted
        assert _score(_job(source=src, remote=True), search_remote=True).explanation["nudge_points"] == 0.0


def test_location_and_seniority_nudges():
    assert _score(_job(loc="Copenhagen, Denmark"), search_location="Copenhagen").explanation["nudge_points"] == 0.5
    assert _score(_job(title="Senior Python Developer")).explanation["nudge_points"] == 0.5   # senior title
    assert _score(_job(title="Junior Python Developer")).explanation["nudge_points"] == 0.0   # no senior token


def test_salary_is_surfaced_display_only():
    ex = _score(_job(salary="600,000 DKK")).explanation
    assert ex["salary"] == "600,000 DKK"
    # salary contributes ZERO score points (it's not a component)
    assert "salary" not in [c["key"] for c in ex["components"]]
    assert _score(_job(salary="")).explanation["salary"] is None


def test_bonus_clamps_at_100():
    # force a near-perfect base so base + full bonus would exceed 100
    prof = _senior_profile()
    j = Job(title="Senior Python Developer", company="X", source="Arbeitnow", remote=True,
            posted="2026-06-15", location="Copenhagen, Denmark",
            description=prof.raw_text)        # identical text → ~max base
    rank_jobs(prof, [j], MatchConfig(today=_TODAY, search_location="Copenhagen", search_remote=True))
    assert j.score <= 100.0
    assert abs(sum(c["points"] for c in j.explanation["components"]) - j.score) < 0.2  # still sums, even clamped
