"""Score-calibration guard: a labeled CV×JD fixture set pins the 0-100 score's meaning.

The fixtures (tests/fixtures/calibration.json) are realistic, Denmark-relevant CVs each
paired with jobs labeled strong / partial / unrelated. These assertions fail if a future
change drifts the calibration — e.g. a clearly-strong match stops landing in the 'strong'
band, an unrelated role creeps up, or the best-matching job is no longer ranked on top.
"""
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from jobfinder.cv_parser import build_profile
from jobfinder.matcher import rank_jobs, MatchConfig, score_band, SCORE_BANDS
from jobfinder.sources.base import Job

_FIXTURES = json.loads((Path(__file__).parent / "fixtures" / "calibration.json").read_text(encoding="utf-8"))
_TODAY = date(2026, 6, 16)
# Derive thresholds from the single source of truth so the guard tracks the bands —
# never duplicate the numbers (a stale literal could pass a real calibration regression).
_BY_KEY = {key: threshold for threshold, key, _ in SCORE_BANDS}
STRONG = _BY_KEY["strong"]
GOOD = _BY_KEY["good"]


def _scored(fixture) -> list[tuple[str, float, str]]:
    """Return (expected_tier, score, band) for every job in a fixture, scored against its CV."""
    profile = build_profile(fixture["cv_text"])
    jobs = [Job(title=j["title"], company="Co", description=j["description"],
                location=j["location"], source="test") for j in fixture["jobs"]]
    # No search location/remote and no posted date → nudges are inert, so we calibrate the
    # base relevance score (recency/fit nudges only ever add a tiny bounded bonus on top).
    rank_jobs(profile, jobs, MatchConfig(today=_TODAY))
    by_title = {jb.title: (jb.score, jb.explanation["band"]) for jb in jobs}
    out = []
    for j in fixture["jobs"]:
        score, band = by_title[j["title"]]
        out.append((j["expected_tier"], score, band))
    return out


_ALL = [(f["domain"], row) for f in _FIXTURES for row in _scored(f)]


# --- the band function itself ---------------------------------------------

def test_score_band_thresholds():
    assert score_band(100)[0] == "strong" and score_band(65)[0] == "strong"
    assert score_band(64.9)[0] == "good" and score_band(40)[0] == "good"
    assert score_band(39.9)[0] == "fair" and score_band(25)[0] == "fair"
    assert score_band(24.9)[0] == "weak" and score_band(0)[0] == "weak"
    assert [b[1] for b in SCORE_BANDS] == ["strong", "good", "fair", "weak"]


# --- calibration against the labeled fixtures ------------------------------

@pytest.mark.parametrize("domain,row", _ALL)
def test_strong_jobs_land_in_strong_band(domain, row):
    tier, score, band = row
    if tier == "strong":
        assert score >= STRONG and band == "strong", f"{domain}: strong job scored {score} ({band})"


@pytest.mark.parametrize("domain,row", _ALL)
def test_unrelated_jobs_stay_out_of_the_top_bands(domain, row):
    tier, score, band = row
    if tier == "unrelated":
        # an unrelated role must never read as a good/strong match
        assert score < GOOD and band in ("weak", "fair"), f"{domain}: unrelated job scored {score} ({band})"


@pytest.mark.parametrize("domain,row", _ALL)
def test_partial_jobs_never_reach_strong(domain, row):
    tier, score, band = row
    if tier == "partial":
        # anchored to the named band (not just the literal threshold) so a band change can't
        # silently let a partial role start reading as a strong match
        assert score < STRONG and band != "strong", f"{domain}: partial job scored {score} ({band})"


def test_top_match_per_cv_is_a_strong_job():
    # for every CV, the highest-scoring posting is one of its 'strong' jobs
    for f in _FIXTURES:
        rows = _scored(f)
        top_tier = max(rows, key=lambda r: r[1])[0]
        assert top_tier == "strong", f"{f['domain']}: top match was '{top_tier}', not strong"


def test_strong_outranks_unrelated_per_cv():
    for f in _FIXTURES:
        rows = _scored(f)
        strong = [s for t, s, _ in rows if t == "strong"]
        unrelated = [s for t, s, _ in rows if t == "unrelated"]
        if strong and unrelated:
            assert max(strong) > max(unrelated), f"{f['domain']}: strong {max(strong)} !> unrelated {max(unrelated)}"
