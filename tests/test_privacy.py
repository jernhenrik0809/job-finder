"""Tests for PII redaction before the optional Claude egress."""
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jobfinder.privacy import redact_pii
from jobfinder.cv_parser import build_profile
from jobfinder.drafts import DraftOptions, generate_llm

JOB = {"title": "Backend Engineer", "company": "Acme", "description": "Python and Django.",
       "matched_skills": ["python", "django"], "missing_skills": ["rust"]}


# --- redactor unit behaviour ----------------------------------------------

def test_redacts_email_phone_url():
    out = redact_pii("Reach me at jane.doe@email.dk or +45 31 22 84 50, portfolio https://jane.dev")
    assert "jane.doe@email.dk" not in out and "+45 31 22 84 50" not in out and "jane.dev" not in out
    assert "[email redacted]" in out and "[contact redacted]" in out and "[link redacted]" in out


def test_redacts_contiguous_and_grouped_phone():
    assert redact_pii("Call 31228450") == "Call [contact redacted]"
    assert redact_pii("Call 31-22-84-50") == "Call [contact redacted]"
    assert redact_pii("Mobile 3122 8450") == "Mobile [contact redacted]"   # Danish 4-4 split


def test_redacts_bare_profile_and_path_links():
    # scheme-less profile URLs are the common CV form and very identifying
    for leak in ("linkedin.com/in/jane-doe", "github.com/janedoe", "janedoe.io/portfolio"):
        assert leak not in redact_pii(f"see {leak}")


def test_keeps_tech_terms_that_look_like_domains():
    # a path-less "domain" is usually a tech term, not a link — must survive
    text = "Skilled in socket.io, ASP.NET, Node.js and Vue.js."
    assert redact_pii(text) == text


def test_keeps_name_dates_amounts_and_metrics():
    text = "Jane Doe — worked 2018-2021, grew traffic 64%, managed a 1,200,000 DKK budget across 10,000 users."
    assert redact_pii(text) == text          # nothing here is contact PII → untouched
    # Danish space-grouped thousands must survive too (don't mistake them for a phone)
    assert redact_pii("budget of 25 000 000 DKK and a 1 200 000 reserve") == "budget of 25 000 000 DKK and a 1 200 000 reserve"


def test_empty_is_safe():
    assert redact_pii("") == "" and redact_pii(None) is None


# --- the redaction actually scrubs the Claude prompt ----------------------

class _Block:
    type = "text"
    def __init__(self, text): self.text = text

class _Resp:
    def __init__(self, text): self.content = [_Block(text)]

class _FakeClient:
    def __init__(self, captured): self.messages = type("M", (), {"create": lambda _s, **k: (captured.update(k) or _Resp("Dear Team,\n\nLetter.\n\nRegards,\nJane Doe"))})()


CV = ("Jane Doe\njane.doe@email.dk\n+45 31 22 84 50\n"
      "Senior Python developer with Django and AWS experience building backend APIs.")


def _system_text(redact: bool) -> str:
    captured = {}
    import anthropic
    with patch.object(anthropic, "Anthropic", lambda *a, **k: _FakeClient(captured)):
        generate_llm(build_profile(CV), JOB, DraftOptions(redact_pii=redact),
                     examples=["Past letter — contact me at me@old.example.com."])
    return captured["system"][0]["text"]


def test_llm_prompt_is_scrubbed_when_enabled():
    sys_text = _system_text(redact=True)
    assert "jane.doe@email.dk" not in sys_text          # CV email gone
    assert "+45 31 22 84 50" not in sys_text            # CV phone gone
    assert "me@old.example.com" not in sys_text         # example email gone too
    assert "Jane Doe" in sys_text                       # name kept (it signs the letter)
    assert "Python" in sys_text                         # substance preserved


def test_llm_prompt_unredacted_by_default():
    sys_text = _system_text(redact=False)
    assert "jane.doe@email.dk" in sys_text              # opt-in: not redacted unless asked
