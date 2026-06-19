"""Tests for bench matching — ranking the house's consultants against an incoming project."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jobfinder.bench import Project, rank_consultants, rank_bench_for_project, project_from_job
from jobfinder.consultants import new_consultant
from jobfinder.sources.base import Job


def test_rank_consultants_orders_by_fit_and_hard_gates_inactive():
    proj = Project(title="Senior Python Engineer", description="Build Django APIs on AWS.",
                   skills=["python", "django", "aws"])
    strong = new_consultant("Strong", skills=["python", "django", "aws"], title="Python Engineer",
                            raw_text="Senior Python engineer; Django REST and AWS for 8 years.")
    weak = new_consultant("Weak", skills=["java"], title="Java Developer",
                          raw_text="Java and Spring Boot developer, mostly backend.")
    inactive = new_consultant("Inactive", skills=["python", "django", "aws"], status="inactive",
                              raw_text="Python Django AWS expert with a decade of delivery.")
    res = rank_consultants(proj, [weak, strong, inactive])

    assert res[0].consultant.name == "Strong" and res[0].eligible
    assert res[0].score > res[1].score
    assert "python" in [s.lower() for s in res[0].matched_skills]
    # inactive is HARD-gated to 0 with a reason and sorted to the bottom (below eligible weak)
    by_name = {r.consultant.name: r for r in res}
    assert by_name["Inactive"].score == 0.0 and not by_name["Inactive"].eligible
    assert by_name["Inactive"].disqualifiers
    assert res[-1].consultant.name == "Inactive"


def test_rank_consultants_availability_and_present_gates():
    proj = Project(title="Data Engineer", skills=["python"], start_date="2026-07-01")
    late = new_consultant("Late", skills=["python"], available_from="2026-09-01", raw_text="python etl")
    hidden = new_consultant("Hidden", skills=["python"], right_to_present=False, raw_text="python etl")
    ready = new_consultant("Ready", skills=["python"], available_from="2026-06-01", raw_text="python etl")
    res = {r.consultant.name: r for r in rank_consultants(proj, [late, hidden, ready])}

    assert not res["Late"].eligible and any("Free from" in d for d in res["Late"].disqualifiers)
    assert not res["Hidden"].eligible and any("forward" in d.lower() for d in res["Hidden"].disqualifiers)
    assert res["Ready"].eligible and res["Ready"].score >= res["Late"].score


def test_rate_ceiling_gates_only_within_currency():
    proj = Project(title="Architect", skills=["python"], rate_ceiling=900.0, currency="DKK")
    over = new_consultant("Over", skills=["python"], sell_rate=1200.0, currency="DKK", raw_text="python")
    under = new_consultant("Under", skills=["python"], sell_rate=800.0, currency="DKK", raw_text="python")
    other_ccy = new_consultant("OtherCcy", skills=["python"], sell_rate=1200.0, currency="EUR", raw_text="python")
    res = {r.consultant.name: r for r in rank_consultants(proj, [over, under, other_ccy])}

    assert not res["Over"].eligible                     # 1200 DKK over 900 DKK ceiling → excluded
    assert res["Under"].eligible                        # 800 DKK under ceiling → ok
    # different currency: never a wrong cross-FX exclusion — stays eligible, flagged as a note
    assert res["OtherCcy"].eligible
    assert any("can't compare" in n for n in res["OtherCcy"].notes)


def test_project_from_job_adapts_posting():
    j = Job(title="Python Consultant", company="Verama", description="Django work for a bank",
            job_skills=["python", "django"], location="Copenhagen", remote=True,
            source="Verama (consulting)", url="https://example.com/x")
    p = project_from_job(j)
    assert p.title == "Python Consultant" and "python" in p.skills
    assert p.remote is True and p.location == "Copenhagen" and p.source.startswith("Verama")


def test_availability_gate_fails_open_on_non_canonical_dates():
    """Non-zero-padded / datetime-form / free-text availability must NOT hard-exclude (fail open),
    and a genuinely-late canonical date must still exclude."""
    proj = Project(title="Engineer", skills=["python"], start_date="2026-12-01")
    nonpadded = new_consultant("NonPadded", skills=["python"], available_from="2026-7-01", raw_text="python")
    datetime_same = new_consultant("Datetime", skills=["python"],
                                   available_from="2026-12-01T09:00:00", raw_text="python")
    freetext = new_consultant("FreeText", skills=["python"], available_from="asap", raw_text="python")
    late = new_consultant("Late", skills=["python"], available_from="2027-03-01", raw_text="python")
    res = {r.consultant.name: r for r in rank_consultants(proj, [nonpadded, datetime_same, freetext, late])}
    assert res["NonPadded"].eligible      # July < December — must not be excluded by string sort
    assert res["Datetime"].eligible       # same calendar day — datetime suffix tolerated
    assert res["FreeText"].eligible       # unparseable → unknown → fail open
    assert not res["Late"].eligible       # genuinely later than the start → still excluded


def test_status_gate_tolerates_casing_and_whitespace():
    proj = Project(title="Engineer", skills=["python"])
    c = new_consultant("Cased", skills=["python"], status=" Active ", raw_text="python")
    res = rank_consultants(proj, [c])
    assert res[0].eligible                 # " Active " is active, not a wrong exclusion


def test_rate_ceiling_currency_match_is_case_insensitive():
    proj = Project(title="Architect", skills=["python"], rate_ceiling=900.0, currency="DKK")
    over = new_consultant("OverLower", skills=["python"], sell_rate=1200.0, currency="dkk", raw_text="python")
    res = rank_consultants(proj, [over])
    assert not res[0].eligible             # 'dkk' == 'DKK' → over-ceiling correctly excluded


def test_rank_bench_for_project_alias_and_empty_bench():
    assert rank_bench_for_project(Project(title="X"), []) == []
