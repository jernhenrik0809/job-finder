"""Generate application drafts (cover letters) for selected roles → the Outbox.

Two backends, mirroring the rest of the app's offline-first design:

* **template** (default, no API key) — personalises a cover letter from the CV
  profile and the job's matched/missing skills. Deterministic, instant, offline.
* **llm** (optional) — Claude (Opus 4.8) when ANTHROPIC_API_KEY is set. Writes a
  genuinely tailored letter and mimics the user's voice from uploaded example
  applications. Falls back to the template generator on any error.

This module only *drafts* applications into an outbox for the user to review,
edit and send themselves — it never auto-submits anywhere.
"""
from __future__ import annotations

import os
import re
import secrets
from dataclasses import dataclass, field, asdict

from .cv_parser import CVProfile

DEFAULT_MODEL = os.environ.get("JOBFINDER_MODEL", "claude-opus-4-8")


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

@dataclass
class DraftOptions:
    tone: str = "professional"     # professional | warm | concise | enthusiastic
    length: str = "standard"       # short | standard
    use_llm: bool = True           # use Claude if available; else template


@dataclass
class ApplicationDraft:
    job_title: str
    company: str
    job_url: str = ""
    job_source: str = ""
    score: float = 0.0
    subject: str = ""
    body: str = ""
    generator: str = "template"    # "template" | "llm"
    status: str = "draft"          # draft | ready
    note: str = ""                 # e.g. a fallback warning
    id: str = field(default_factory=lambda: secrets.token_urlsafe(8))

    def to_dict(self) -> dict:
        return asdict(self)


def llm_available() -> bool:
    """True if a Claude API key is present (the SDK is an optional dependency)."""
    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        return False
    try:
        import anthropic  # noqa: F401
        return True
    except ImportError:
        return False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _job_get(job: dict, *keys, default=""):
    for k in keys:
        v = job.get(k)
        if v:
            return v
    return default


def _subject(title: str, company: str) -> str:
    if company:
        return f"Application for {title} — {company}"
    return f"Application for {title}"


# ---------------------------------------------------------------------------
# Template (offline) generator
# ---------------------------------------------------------------------------

_GREETING = {
    "professional": "Dear Hiring Team",
    "warm": "Hello",
    "concise": "Dear Hiring Manager",
    "enthusiastic": "Dear Hiring Team",
}
_SIGNOFF = {
    "professional": "Kind regards",
    "warm": "Warm regards",
    "concise": "Best regards",
    "enthusiastic": "With enthusiasm",
}


def _article(word: str) -> str:
    return "an" if word[:1].lower() in "aeiou" else "a"


def _list_phrase(items: list[str], limit: int = 4) -> str:
    items = [i for i in items][:limit]
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + f" and {items[-1]}"


def generate_template(profile: CVProfile, job: dict, options: DraftOptions) -> ApplicationDraft:
    title = _job_get(job, "title", default="this role")
    company = _job_get(job, "company")
    matched = job.get("matched_skills") or []
    name = profile.name or "Your name"
    cv_title = (profile.titles[0].title() if profile.titles else "professional")
    years = profile.years_experience
    tone = options.tone if options.tone in _GREETING else "professional"

    greeting = _GREETING[tone] + (f" at {company}" if company and tone != "concise" else "")
    company_ref = company or "your team"

    role_l = cv_title.lower()
    exp_bit = (f"{years} years of experience as {_article(role_l)} {role_l}"
               if years else f"experience as {_article(role_l)} {role_l}")
    skills_phrase = _list_phrase(matched) or _list_phrase(profile.skills)

    para_open = (
        f"I am writing to express my interest in the {title} position"
        + (f" at {company}" if company else "")
        + f". With {exp_bit}, I believe I would be a strong fit for your team."
    )

    if skills_phrase:
        para_fit = (
            f"Your role calls for {skills_phrase} — areas I work with directly. "
            f"I am confident I can apply this experience to contribute quickly at {company_ref}."
        )
    else:
        para_fit = (
            f"My background aligns well with what you are looking for, and I am confident "
            f"I can contribute quickly at {company_ref}."
        )

    para_close = (
        f"I would welcome the opportunity to discuss how my background can support {company_ref}'s goals. "
        f"Thank you for considering my application."
    )

    if options.length == "short":
        paragraphs = [para_open, para_fit, para_close]
    else:
        extra_skills = _list_phrase([s for s in profile.skills if s not in matched], limit=3)
        extra = (
            f"I also bring hands-on experience with {extra_skills}, "
            "and a track record of collaborating across teams to deliver results."
            if extra_skills else
            "I bring a track record of collaborating across teams to deliver results."
        )
        paragraphs = [para_open, para_fit, extra, para_close]

    body = (
        f"{greeting},\n\n"
        + "\n\n".join(p for p in paragraphs if p)
        + f"\n\n{_SIGNOFF[tone]},\n{name}"
    )

    return ApplicationDraft(
        job_title=title, company=company, job_url=_job_get(job, "url"),
        job_source=_job_get(job, "source"), score=float(job.get("score") or 0),
        subject=_subject(title, company), body=body, generator="template",
    )


# ---------------------------------------------------------------------------
# Claude (LLM) generator
# ---------------------------------------------------------------------------

_SYSTEM_BASE = (
    "You are an expert career writer helping a candidate apply to jobs. "
    "Write a concise, specific, and genuine cover letter for the given job, grounded ONLY in "
    "the candidate's real CV — never invent experience, employers, or credentials. "
    "Address the role's actual requirements and connect them to the candidate's real skills. "
    "Avoid clichés and generic filler. Output ONLY the letter body (no subject line, no commentary)."
)


def _length_hint(length: str) -> str:
    return "Keep it short: 3 short paragraphs, ~150 words." if length == "short" \
        else "Aim for 4 short paragraphs, ~220-280 words."


def _tone_hint(tone: str) -> str:
    return {
        "professional": "Tone: professional and confident.",
        "warm": "Tone: warm, personable, and human.",
        "concise": "Tone: crisp and to the point.",
        "enthusiastic": "Tone: enthusiastic and energetic, while staying credible.",
    }.get(tone, "Tone: professional and confident.")


def generate_llm(profile: CVProfile, job: dict, options: DraftOptions,
                 examples: list[str] | None = None,
                 model: str = DEFAULT_MODEL) -> ApplicationDraft:
    """Generate a tailored letter with Claude. Raises on failure (caller may fall back)."""
    import anthropic

    client = anthropic.Anthropic()

    title = _job_get(job, "title", default="this role")
    company = _job_get(job, "company")
    job_desc = _job_get(job, "description")[:6000]
    matched = ", ".join((job.get("matched_skills") or [])[:12])
    missing = ", ".join((job.get("missing_skills") or [])[:8])

    # Stable system prefix (instructions + style examples + CV) — identical across all
    # drafts in a batch, so prompt-cache it.
    system_parts = [_SYSTEM_BASE]
    if examples:
        joined = "\n\n---\n\n".join(e.strip()[:4000] for e in examples[:3])
        system_parts.append(
            "STYLE REFERENCE — match the voice, structure and tone of these example "
            f"applications the candidate wrote, but write fresh content for THIS job:\n\n{joined}"
        )
    system_parts.append(
        "CANDIDATE CV (the only source of truth about the candidate):\n\n"
        + (profile.raw_text or "")[:8000]
    )
    system_blocks = [{"type": "text", "text": "\n\n========\n\n".join(system_parts),
                      "cache_control": {"type": "ephemeral"}}]

    user = (
        f"Write a cover letter for this job.\n\n"
        f"Job title: {title}\n"
        f"Company: {company or 'the company'}\n"
        f"Candidate name (sign off with this): {profile.name or 'the candidate'}\n"
        f"Skills the candidate already has that this job wants: {matched or '(infer from CV)'}\n"
        f"Skills the job wants that the CV does not show (do NOT claim these; you may note eagerness to grow): {missing or '(none notable)'}\n\n"
        f"{_tone_hint(options.tone)} {_length_hint(options.length)}\n\n"
        f"Job description:\n{job_desc or '(no description provided — rely on the title)'}"
    )

    resp = client.messages.create(
        model=model,
        max_tokens=1400,
        system=system_blocks,
        messages=[{"role": "user", "content": user}],
    )
    body = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text").strip()
    if not body:
        raise RuntimeError("Empty response from the model.")

    return ApplicationDraft(
        job_title=title, company=company, job_url=_job_get(job, "url"),
        job_source=_job_get(job, "source"), score=float(job.get("score") or 0),
        subject=_subject(title, company), body=body, generator="llm",
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def generate_draft(profile: CVProfile, job: dict, options: DraftOptions,
                   examples: list[str] | None = None) -> ApplicationDraft:
    """Generate one draft, using Claude when requested+available, else the template."""
    if options.use_llm and llm_available():
        try:
            return generate_llm(profile, job, options, examples=examples)
        except Exception as e:  # never let a model hiccup break the batch
            draft = generate_template(profile, job, options)
            draft.note = f"Claude unavailable ({type(e).__name__}); used the offline template instead."
            return draft
    return generate_template(profile, job, options)
