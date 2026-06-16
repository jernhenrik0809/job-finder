"""Tests for résumé tailoring (bullet ranking, provenance, mocked Claude rewrite)."""
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jobfinder.cv_parser import build_profile
from jobfinder.tailor import tailor_resume, generate_tailoring, _segment_bullets

CV = """Jane Doe
Senior Software Engineer
SKILLS
Python, Django, AWS
EXPERIENCE
- Built scalable Python microservices serving 10M requests with Django and AWS
- Led migration to Kubernetes cutting infra costs 30 percent
- Mentored a team of five engineers on backend best practices
- Designed marketing email campaigns and managed social media posts
phone: 555-1234
"""

JOB = {"title": "Backend Python Engineer", "company": "Acme",
       "description": "Python, Django, AWS, microservices, scalable backend systems.",
       "matched_skills": ["python", "django", "aws"], "missing_skills": ["rust"]}


def test_segment_bullets_skips_headers_contact_and_skill_lists():
    b = _segment_bullets(CV)
    assert any("microservices" in x for x in b)
    assert "SKILLS" not in b and "EXPERIENCE" not in b
    assert not any("phone" in x.lower() for x in b)
    # the comma-separated skills line is not an accomplishment bullet
    assert not any(x.startswith("Python, Django, AWS") for x in b)
    # ...but a sentence that happens to contain commas is kept
    kept = _segment_bullets("- Led teams across Python, Go, and Rust to ship three production services")
    assert kept and "Led teams" in kept[0]
    # a terse verb-led achievement with short comma clauses is kept (not mistaken for a skills list)
    terse = _segment_bullets("- Built APIs, shipped features, led code reviews")
    assert terse, "verb-led terse achievement should survive the skills-list filter"
    # while a true skills line (no leading verb, short entries) is still dropped
    assert _segment_bullets("Python, Django, Flask, FastAPI, AWS, Docker, Redis") == []
    assert all(len(x) >= 25 and not x.startswith("-") for x in b)


def test_tailor_ranks_relevant_bullet_first_with_provenance():
    r = tailor_resume(build_profile(CV), JOB)
    assert r["bullets"]
    top = r["bullets"][0]
    assert isinstance(top["text"], str) and "source_index" in top      # provenance
    texts = [b["text"] for b in r["bullets"]]
    py_i = next(i for i, t in enumerate(texts) if "Python microservices" in t)
    mk_i = next((i for i, t in enumerate(texts) if "marketing" in t.lower()), len(texts))
    assert py_i < mk_i                                                  # python ranks above marketing


def test_tailor_emphasize_and_gaps():
    r = tailor_resume(build_profile(CV), JOB)
    assert "python" in [s.lower() for s in r["emphasize_skills"]]
    assert "rust" in r["gaps"]
    assert r["generator"] == "template"


class _Block:
    type = "text"
    def __init__(self, t): self.text = t

class _Resp:
    def __init__(self, t): self.content = [_Block(t)]

class _FakeClient:
    class messages:
        @staticmethod
        def create(**k):
            return _Resp("\n".join(f"{i}. Rewrote bullet {i}" for i in range(1, 9)))


def test_generate_tailoring_llm_rewrites_each_bullet_grounded(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    import anthropic
    with patch.object(anthropic, "Anthropic", lambda *a, **k: _FakeClient()):
        r = generate_tailoring(build_profile(CV), JOB, use_llm=True)
    assert r["generator"] == "llm"
    assert any("rewritten" in b for b in r["bullets"])
    assert all("text" in b for b in r["bullets"])                       # original kept as provenance


def test_generate_tailoring_without_key_is_template(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    r = generate_tailoring(build_profile(CV), JOB, use_llm=True)
    assert r["generator"] == "template"
    assert all("rewritten" not in b for b in r["bullets"])
