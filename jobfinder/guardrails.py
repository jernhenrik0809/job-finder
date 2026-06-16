"""Offline guardrails that verify a cover letter before it goes out.

The app promises it never fabricates — these checks turn that promise from a prompt
instruction into a *verified property* that runs on every draft, regardless of which
generator (template or Claude) produced it:

* **placeholder** — an unresolved bracketed placeholder ("[Company]", "[Your Name]")
  means the letter isn't ready to send.
* **unsupported_skill** — a skill the *job* asks for that is **not** on the candidate's CV
  (a "gap" skill) but is nonetheless named in the letter. This is the fabrication surface:
  the user should make sure such a skill is framed as something they're eager to learn, not
  a claim of experience. Scoping to the job's gap skills keeps the check high-signal and
  avoids flagging ordinary prose (e.g. the verb "express" is not a claim to know Express.js).

Pure, dependency-light, and unit-tested without a server. The web layer attaches the
findings to the letter responses; the UI renders them as badges.
"""
from __future__ import annotations

import re
from collections.abc import Iterable

from .skills import canonical, non_technical_skills, skill_spans

# Matches only bracketed text that carries a placeholder cue word, so legitimate prose
# like "[top 5%]" or "array[i]" is not flagged. This is the single source of truth for
# placeholder detection (drafts.py imports it).
PLACEHOLDER_RE = re.compile(
    r"\[[^\]\n]*\b(?:your\s+name|company|role|position|platform|employer|"
    r"hiring\s+manager|title|team|date|address|insert|todo|tbd|here|xx+)\b[^\]\n]*\]",
    re.I,
)

# Possession cues — a gap skill is only treated as a *claim* if one of these appears
# just before it (e.g. "expert in Kubernetes", "strong Go", "5 years of Rust"), or it
# is immediately followed by a claim word ("Rust expertise"). This keeps the check from
# firing on ordinary prose ("go above and beyond") or growth language ("eager to learn
# Kubernetes" — no possession cue, so not flagged).
# A possession cue, then at most a short connective ("in"/"with"/"of"/…) of letters and
# spaces before the skill. Punctuation breaks the window, so a cue in a previous clause
# ("I'm strong. I will go…") doesn't leak onto the next skill.
_CLAIM_BEFORE = re.compile(
    r"(?:experienced?|expert(?:ise)?|proficien\w*|skilled|fluent|master(?:y|ed)?|"
    r"hands[\s-]?on|versed|seasoned|specialist|specializ\w*|strong|solid|extensive|"
    r"advanced|deep|competent|adept|years?|knowledge|background|familiar|comfortable)"
    r"[A-Za-z\s]{0,14}$",
    re.I,
)
_CLAIM_AFTER = re.compile(r"^\W*(?:experience|expertise|developer|engineer|skills?)\b", re.I)
_BEFORE_WINDOW = 45
_AFTER_WINDOW = 22


def check_letter(body: str, gap_skills: Iterable[str] | None = None) -> list[dict]:
    """Return guardrail findings for a letter body.

    Each finding is ``{type, severity, message, items}``. ``gap_skills`` is the set of
    skills the job wants that are **not** on the candidate's CV (the job's "missing"
    skills); a letter that names one of these is flagged. When omitted/empty the
    unsupported-skill check is skipped, but the placeholder check still runs.
    """
    findings: list[dict] = []
    if not body:
        return findings

    placeholders = sorted({m.group(0) for m in PLACEHOLDER_RE.finditer(body)})
    if placeholders:
        findings.append({
            "type": "placeholder",
            "severity": "high",
            "message": "Fill in or remove these placeholders before sending.",
            "items": placeholders[:8],
        })

    named = _claimed_gap_skills(body, gap_skills)
    if named:
        findings.append({
            "type": "unsupported_skill",
            "severity": "medium",
            "message": ("Your letter appears to claim skills this role wants that aren't on your CV — "
                        "make sure they're framed as skills you're eager to learn, not experience."),
            "items": named[:10],
        })

    return findings


def _claimed_gap_skills(body: str, gap_skills: Iterable[str] | None) -> list[str]:
    """Gap skills the letter appears to *claim* (named in a possession context).

    Precision-first: excludes soft skills / human languages (prose-common, not CV
    credentials), requires a possession cue around the mention, and canonicalises both
    sides. ``isinstance`` guards against a malformed (non-string) skill crashing the run.
    """
    if not gap_skills:
        return []
    gap_set = {canonical(s) for s in gap_skills if isinstance(s, str) and s.strip()}
    gap_set -= non_technical_skills()
    if not gap_set:
        return []

    out: list[str] = []
    seen: set[str] = set()
    for canon, start, end in skill_spans(body):
        if canon not in gap_set or canon in seen:
            continue
        before = body[max(0, start - _BEFORE_WINDOW):start]
        after = body[end:end + _AFTER_WINDOW]
        if _CLAIM_BEFORE.search(before) or _CLAIM_AFTER.match(after):
            seen.add(canon)
            out.append(canon)
    return out
