"""Tests for application-draft generation (template + mocked Claude path)."""
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jobfinder.cv_parser import build_profile, extract_text
from jobfinder.drafts import (
    DraftOptions, generate_template, generate_llm, generate_draft, llm_available,
)

SAMPLE = Path(__file__).parent / "sample_cv.txt"
JOB = {
    "title": "Senior Python Engineer",
    "company": "Acme AI",
    "url": "https://example.com/job/1",
    "source": "LinkedIn",
    "score": 82.0,
    "description": "We need Python, Django, AWS and Kubernetes for our backend team.",
    "matched_skills": ["python", "django", "aws"],
    "missing_skills": ["rust"],
}


def _profile():
    return build_profile(extract_text(SAMPLE))


# --- name detection -------------------------------------------------------

def test_name_detected_from_cv():
    assert _profile().name == "Jane Doe"


def test_name_detected_with_honorific():
    p = build_profile("Dr. Sophia Almeida\nAI Ethics Researcher\nCambridge, UK")
    assert p.name == "Dr. Sophia Almeida"


# --- template generation --------------------------------------------------

def test_template_draft_personalised():
    d = generate_template(_profile(), JOB, DraftOptions(tone="professional", length="standard"))
    assert d.generator == "template"
    assert "Senior Python Engineer" in d.subject
    assert "Acme AI" in d.subject
    assert "Jane Doe" in d.body            # signs off with the candidate's name
    assert "Acme AI" in d.body             # references the company
    # mentions at least one matched skill
    assert any(s in d.body.lower() for s in ("python", "django", "aws"))
    assert d.job_url == "https://example.com/job/1"


def test_template_short_is_shorter_than_standard():
    p = _profile()
    short = generate_template(p, JOB, DraftOptions(length="short"))
    standard = generate_template(p, JOB, DraftOptions(length="standard"))
    assert len(short.body) < len(standard.body)


def test_template_tones_change_greeting():
    p = _profile()
    warm = generate_template(p, JOB, DraftOptions(tone="warm"))
    prof = generate_template(p, JOB, DraftOptions(tone="professional"))
    assert warm.body != prof.body


# --- LLM path (mocked) ----------------------------------------------------

class _Block:
    type = "text"
    def __init__(self, text): self.text = text

class _Resp:
    def __init__(self, text): self.content = [_Block(text)]

class _FakeMessages:
    def __init__(self, captured): self._captured = captured
    def create(self, **kwargs):
        self._captured.update(kwargs)
        return _Resp("Dear Hiring Team at Acme AI,\n\nThis is a tailored letter.\n\nKind regards,\nJane Doe")

class _FakeClient:
    def __init__(self, captured): self.messages = _FakeMessages(captured)


def test_generate_llm_uses_examples_and_cv(monkeypatch=None):
    captured = {}
    import anthropic
    with patch.object(anthropic, "Anthropic", lambda *a, **k: _FakeClient(captured)):
        d = generate_llm(_profile(), JOB, DraftOptions(),
                         examples=["My previous great cover letter, very warm and specific."])
    assert d.generator == "llm"
    assert "tailored letter" in d.body
    # system prompt should carry the CV and the style example, and be cache-controlled
    system = captured["system"]
    sys_text = system[0]["text"]
    assert "Jane Doe" in sys_text                      # CV included
    assert "previous great cover letter" in sys_text   # example included
    assert system[0]["cache_control"] == {"type": "ephemeral"}
    assert captured["model"]


def test_generate_draft_without_key_falls_back_to_template(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    assert llm_available() is False
    d = generate_draft(_profile(), JOB, DraftOptions(use_llm=True))
    assert d.generator == "template"   # no key → template, no crash
