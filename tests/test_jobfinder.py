"""Unit tests for the core job-finder logic (no network required)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jobfinder.skills import extract_skills, skill_overlap
from jobfinder.cv_parser import build_profile, extract_text, looks_empty
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
