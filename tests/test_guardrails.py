"""Tests for the offline cover-letter guardrails (placeholders + unsupported skills)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jobfinder.guardrails import check_letter, PLACEHOLDER_RE

# the job wants these but they're NOT on the candidate's CV (the "gap" skills)
GAP_SKILLS = ["kubernetes", "rust"]


def _skill_items(body, gap):
    f = [x for x in check_letter(body, gap) if x["type"] == "unsupported_skill"]
    return f[0]["items"] if f else []


def test_clean_letter_has_no_findings():
    body = "Dear Hiring Team,\nI build Python and Django services on AWS with PostgreSQL.\nKind regards,\nJane"
    assert check_letter(body, GAP_SKILLS) == []


def test_flags_unresolved_placeholders():
    body = "Dear Hiring Team at [Company],\nI'd love to join [Platform].\nRegards,\n[Your Name]"
    findings = check_letter(body, GAP_SKILLS)
    ph = next(f for f in findings if f["type"] == "placeholder")
    assert ph["severity"] == "high"
    assert "[Company]" in ph["items"] and "[Your Name]" in ph["items"]


def test_placeholder_regex_ignores_legitimate_brackets():
    # bracketed prose without a placeholder cue word must NOT be flagged
    assert not PLACEHOLDER_RE.search("I ranked in the [top 5%] of my cohort and tuned array[i].")


def test_flags_gap_skill_claimed_with_possession_cue():
    # "deep Kubernetes" and "Rust expertise" are possession claims → flagged
    body = "I have deep Kubernetes and Rust expertise, alongside my Python work."
    items = _skill_items(body, GAP_SKILLS)
    assert "kubernetes" in items and "rust" in items
    assert "python" not in items                     # not a gap skill


def test_requires_a_claim_context_not_mere_mention():
    # the job wants Go, but ordinary prose / growth language must NOT be flagged
    assert _skill_items("I would go above and beyond for this team.", ["go"]) == []
    assert _skill_items("I am eager to learn Kubernetes.", ["kubernetes"]) == []
    # a real possession claim IS flagged
    assert _skill_items("I am an expert in Go.", ["go"]) == ["go"]
    assert _skill_items("Proficient with Kubernetes in production.", ["kubernetes"]) == ["kubernetes"]


def test_excludes_soft_skills_and_languages_from_claims():
    # soft skills are prose-common and not CV credentials → never flagged even with a cue
    body = "I bring strong leadership, clear communication and fluent Spanish."
    assert _skill_items(body, ["leadership", "communication", "spanish"]) == []


def test_canonicalises_alias_gap_skills():
    # a raw-alias gap skill ('golang') still matches a real claim ('Golang')
    assert _skill_items("I have 5 years of Golang experience.", ["golang"]) == ["go"]


def test_tolerates_non_string_gap_items():
    # a malformed (client-supplied) skills list must not crash the check
    assert _skill_items("I am an expert in Rust.", ["rust", None, 123, {"x": 1}]) == ["rust"]


def test_skill_check_skipped_without_gap_skills():
    body = "I have deep Kubernetes and Rust expertise."
    findings = check_letter(body, None)            # no job context → don't flag skills
    assert all(f["type"] != "unsupported_skill" for f in findings)


def test_empty_body_is_clean():
    assert check_letter("", GAP_SKILLS) == []
