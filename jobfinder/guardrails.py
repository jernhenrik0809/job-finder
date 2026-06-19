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


# ---------------------------------------------------------------------------
# Proposal QA — a house bid is higher-stakes than a personal letter: the author (house) is
# distinct from the subjects (consultants), the output goes out under a durable BRAND, and the
# highest-value DK/TED bids are Danish. So the proposal gate (a) verifies a claimed capability
# is attributable to a SPECIFIC named proposed consultant (not merely "someone on the bench"),
# (b) runs its possession cues in BOTH English and Danish, and (c) fails CLOSED — when the team
# has no recorded skills to verify against, capability claims are blocked, not waved through.
# check_letter above is intentionally left untouched (its calibration is English/first-person).
# ---------------------------------------------------------------------------

# English + Danish possession cues (proposals may be written in either language).
_CLAIM_BEFORE_ML = re.compile(
    r"(?:experienced?|expert(?:ise)?|proficien\w*|skilled|fluent|master\w*|hands[\s-]?on|versed|"
    r"seasoned|specialist|specializ\w*|strong|solid|extensive|advanced|deep|competent|adept|"
    r"years?|knowledge|background|familiar|comfortable|certified|led|delivered|built|"
    r"erfaren|erfaring|ekspert|kompetent|stærk|dyb|solid|specialist|certificeret|kendskab|"
    r"baggrund|fortrolig|års?|leveret|byggede|bygget|kompetencer)"
    r"[A-Za-zæøåÆØÅ\s]{0,16}$",
    re.I,
)
_CLAIM_AFTER_ML = re.compile(
    r"^\W*(?:experience|expertise|developer|engineer|skills?|erfaring|ekspert|udvikler|"
    r"ingeniør|kompetencer)\b", re.I)
# Action/assignment cues: a bid often states a capability as an action ("Anna will handle the
# Kubernetes cluster", "leder Rust-teamet") rather than an adjective — treat those as claims too.
_CLAIM_VERB_ML = re.compile(
    r"\b(?:handl\w*|own(?:s|ed|ing)?|lead(?:s|ing)?|led|architect\w*|implement\w*|deliver\w*|"
    r"manage\w*|maintain\w*|responsible|drive[ns]?|driving|set\s+up|st(?:an|oo)d\s+up|"
    r"håndter\w*|leder|ledede|ansvarlig|implementer\w*|leverer|leveret|vedligehold\w*|driver)"
    r"[A-Za-zæøåÆØÅ\s,.\-]{0,40}$", re.I)
_ATTR_WINDOW = 90          # how far back to look for a consultant's name before a skill claim


def _consultant_view(c) -> tuple[str, set[str]]:
    """(first_name_lower, canonical_skill_set) from a Consultant object or a plain dict."""
    name = (getattr(c, "name", None) if not isinstance(c, dict) else c.get("name")) or ""
    skills = (getattr(c, "skills", None) if not isinstance(c, dict) else c.get("skills"))
    if not isinstance(skills, (list, tuple, set)):    # a stray string/None must not become char-skills
        skills = []
    cset = {canonical(s) for s in skills if isinstance(s, str) and s.strip()}
    first = name.strip().split()[0].lower() if name.strip() else ""
    return first, cset


def _claimed_skill_spans(body: str) -> list[tuple[str, int, int]]:
    """Every (canonical_skill, start, end) named in a possession/claim context (EN or DA),
    excluding soft skills / human languages. Deduped to first mention per skill."""
    out: list[tuple[str, int, int]] = []
    seen: set[str] = set()
    soft = non_technical_skills()
    for canon, start, end in skill_spans(body):
        if canon in seen or canon in soft:
            continue
        before = body[max(0, start - _BEFORE_WINDOW):start]
        after = body[end:end + _AFTER_WINDOW]
        if (_CLAIM_BEFORE_ML.search(before) or _CLAIM_AFTER_ML.match(after)
                or _CLAIM_VERB_ML.search(before)):
            seen.add(canon)
            out.append((canon, start, end))
    return out


def check_proposal(body: str, consultants: Iterable | None = None,
                   *, require_grounding: bool = True) -> list[dict]:
    """Verify a house proposal before export. Returns findings ``{type, severity, blocking,
    message, items}``. Blocking findings must stop export (see :func:`has_blocking`).

    ``consultants`` is the list of PROPOSED consultants (objects or dicts with name+skills) —
    the only people a capability may be attributed to.

    LIMITATION (by design): this is a high-precision *assist*, not a complete oracle. It detects
    capability claims phrased with a possession/action cue around a skill the curated skills
    dictionary recognises (English + Danish). It therefore CANNOT see a fabricated capability
    whose name is outside that dictionary (a niche/proprietary tool or certification), nor an
    unusually phrased claim. That residual risk is covered by the product's real guarantee — a
    human reviews and sends every proposal; this gate never auto-approves anything."""
    findings: list[dict] = []
    if not body:
        return findings

    placeholders = sorted({m.group(0) for m in PLACEHOLDER_RE.finditer(body)})
    if placeholders:
        findings.append({"type": "placeholder", "severity": "high", "blocking": True,
                         "message": "Fill in or remove these placeholders before sending.",
                         "items": placeholders[:8]})

    team = [_consultant_view(c) for c in (consultants or [])]
    union: set[str] = set()
    for _first, cset in team:
        union |= cset
    claimed = _claimed_skill_spans(body)

    if claimed:
        if not union:
            # Fail CLOSED: claims are made but there is nothing to verify them against.
            findings.append({"type": "no_grounding", "severity": "high", "blocking": True,
                             "message": ("The proposal claims capabilities but the proposed "
                                         "consultants have no recorded skills to verify against — "
                                         "add their skills/CV before exporting."),
                             "items": [c for c, _, _ in claimed][:10]})
        else:
            unsupported = sorted({c for c, _, _ in claimed if c not in union})
            if unsupported:
                findings.append({"type": "unsupported_capability", "severity": "high", "blocking": True,
                                 "message": ("The proposal claims capabilities none of the proposed "
                                             "consultants have on record — remove them or add a "
                                             "consultant who has them."),
                                 "items": unsupported[:10]})
            # Misattribution: a skill claim sits right after a SPECIFIC consultant's name, but that
            # named person doesn't have it (someone else on the team does). Best-effort, conservative.
            misattr: list[str] = []
            for canon, start, _end in claimed:
                if canon not in union:
                    continue
                before = body[max(0, start - _ATTR_WINDOW):start].lower()
                # word-boundary name match so "per" doesn't match inside "performed"/"expert"
                near = [(first, cset) for first, cset in team
                        if first and re.search(r"\b" + re.escape(first) + r"\b", before)]
                # flag when a named consultant is nearby and NONE of the matched same-named
                # candidates has the skill (handles shared first names instead of skipping).
                if near and all(canon not in cset for _f, cset in near):
                    item = f"{near[0][0]}: {canon}"
                    if item not in misattr:
                        misattr.append(item)
            if misattr:
                findings.append({"type": "misattributed_skill", "severity": "high", "blocking": True,
                                 "message": ("A capability is attributed to a named consultant who "
                                             "does not have it on record — fix the attribution."),
                                 "items": misattr[:10]})
    return findings


def has_blocking(findings: Iterable[dict]) -> bool:
    """True if any finding must block export (the 'drafts, never sends a fabrication' line)."""
    return any(f.get("blocking") for f in (findings or []))
