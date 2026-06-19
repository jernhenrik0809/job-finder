"""Bench matching — rank the house's CONSULTANTS against one incoming PROJECT (an ingested
posting or a pasted brief). The inverse of ``matcher.rank_jobs``: there, many jobs are scored
against one CV; here, many consultants are scored against one project, in ONE shared TF-IDF
space so the scores are comparable across consultants (looping ``rank_jobs`` per consultant
would refit the vectorizer each call, making the cosines incomparable).

Two things the job-seeker matcher does NOT have, and that MUST stay separate from it:
  * a PRE-RANK ELIGIBILITY gate that can drop a consultant to score 0 with an explicit reason
    (inactive / not-presentable / availability / rate ceiling) — a HARD exclusion, categorically
    unlike ``matcher.py``'s bounded, never-penalizing nudges;
  * these functions take already-loaded plain objects and NEVER touch the store, so the
    expensive vectorization never runs while a store lock is held.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from .consultants import Consultant
from .matcher import MatchConfig, _tfidf_similarities, _title_score
from .skills import extract_skills, skill_overlap


@dataclass
class Project:
    """A unit of work to staff — adapted from an ingested posting or a pasted brief."""
    title: str
    description: str = ""
    skills: list[str] = field(default_factory=list)
    location: str = ""
    remote: bool = False
    rate_ceiling: float | None = None      # max sell rate the client will pay
    currency: str = ""                     # ISO 4217; rate compared within-currency only
    start_date: str = ""                   # ISO; the consultant must be free by then
    end_date: str = ""
    required_clearance: str = ""           # free-text; "" = none required
    source: str = ""
    url: str = ""


@dataclass
class BenchMatch:
    consultant: Consultant
    score: float                           # 0-100; forced to 0 when ineligible
    eligible: bool
    disqualifiers: list[str]               # HARD reasons the consultant was excluded (else [])
    matched_skills: list[str]              # project skills this consultant covers
    missing_skills: list[str]              # project skills this consultant lacks
    reasons: list[str]                     # plain-English why-this-rank
    notes: list[str]                       # soft flags for the human (never exclude on their own)


def project_from_job(job) -> Project:
    """Adapt an ingested ``Job``/posting into a Project. Rate & dates live in free text for most
    sources today, so they stay unset here (a later phase enriches the ``Job`` model); a pasted
    brief can populate them directly."""
    return Project(
        title=(getattr(job, "title", "") or ""),
        description=(getattr(job, "description", "") or ""),
        skills=list(getattr(job, "job_skills", []) or []),
        location=(getattr(job, "location", "") or ""),
        remote=bool(getattr(job, "remote", False)),
        source=(getattr(job, "source", "") or ""),
        url=(getattr(job, "url", "") or ""),
    )


def _as_date(s: str) -> date | None:
    """Parse an ISO date, tolerating a datetime suffix (mirrors ``matcher._parse_posted``).
    Returns None on empty/malformed/free-text input so the eligibility gate fails OPEN on
    unknown values rather than mis-comparing strings — raw string compare mis-sorts a
    non-zero-padded ("2026-7-01") or datetime-form ("2026-07-01T09:00") value and would
    HARD-exclude a consultant who is actually free."""
    raw = (s or "").strip()[:10]
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def _eligibility(c: Consultant, project: Project) -> tuple[list[str], list[str]]:
    """Return (disqualifiers, soft_notes). A disqualifier is a HARD exclusion (score 0); a soft
    note is surfaced for the human but never excludes. Fails OPEN on unknown/unparseable data
    (owner steer: don't exclude on missing fields) and never compares rates across currencies."""
    dq: list[str] = []
    notes: list[str] = []
    if (c.status or "").strip().lower() != "active":         # tolerate casing/whitespace
        dq.append("Marked inactive on the bench")
    if not c.right_to_present:
        dq.append("Not cleared to put forward")
    # Availability — only when BOTH the project start and the consultant's window PARSE to real
    # dates; an unparseable value is treated as unknown (fail open), not a wrong exclusion.
    start = _as_date(project.start_date)
    avail_from, avail_until = _as_date(c.available_from), _as_date(c.available_until)
    if start and avail_from and avail_from > start:
        dq.append(f"Free from {c.available_from}; project starts {project.start_date}")
    if start and avail_until and avail_until < start:
        dq.append(f"Booked until {c.available_until}; project starts {project.start_date}")
    # Rate ceiling — only when both rates are known AND in the same currency (case-normalized;
    # never a wrong cross-FX comparison — surface a note instead).
    if project.rate_ceiling is not None and c.sell_rate is not None:
        pc, cc = (project.currency or "").strip().upper(), (c.currency or "").strip().upper()
        if pc and cc and pc == cc:
            if c.sell_rate > project.rate_ceiling:
                dq.append(f"Rate {c.sell_rate:g} {c.currency} over ceiling {project.rate_ceiling:g}")
        elif pc and cc and pc != cc:
            notes.append(f"Rate in {c.currency} vs ceiling in {project.currency} — can't compare")
    if project.required_clearance and not c.clearance:
        notes.append("Project may need a clearance — confirm with the consultant")
    return dq, notes


def rank_consultants(project: Project, consultants: list[Consultant],
                     config: MatchConfig | None = None) -> list[BenchMatch]:
    """Score every consultant against the project in ONE shared TF-IDF space; ineligible
    consultants are forced to 0 with explicit disqualifiers. Sorted best-first, eligible
    candidates always above ineligible ones. Pure function — never touches the store."""
    config = config or MatchConfig()
    if not consultants:
        return []

    project_text = f"{project.title}. {project.description}".strip()
    proj_skills = project.skills or extract_skills(project_text)
    texts = [c.match_text() for c in consultants]

    raw_sims, scale = _tfidf_similarities(project_text, texts)   # ONE shared space → comparable
    text_sims = [min(1.0, raw / scale) if scale else 0.0 for raw in raw_sims]

    results: list[BenchMatch] = []
    for c, text_sim in zip(consultants, text_sims):
        matched, missing = skill_overlap(c.skills, proj_skills)   # project skills the consultant has
        title_sim = _title_score([c.title] if c.title else [], project.title)

        comps = [(text_sim, config.w_text), (title_sim, config.w_title)]
        if proj_skills:
            # Recall-oriented (mirror rank_jobs): covering the most important ~12 required
            # skills counts as full marks, with a floor of 4 so a sparse brief isn't over-rewarded.
            denom = max(4, min(len(proj_skills), 12))
            comps.append((min(1.0, len(matched) / denom), config.w_skills))
        wsum = sum(w for _, w in comps) or 1.0
        base = round(max(0.0, min(1.0, sum(v * w for v, w in comps) / wsum)) * 100, 1)

        dq, notes = _eligibility(c, project)
        eligible = not dq
        results.append(BenchMatch(
            consultant=c, score=base if eligible else 0.0, eligible=eligible, disqualifiers=dq,
            matched_skills=matched, missing_skills=missing, notes=notes,
            reasons=_bench_reasons(text_sim, matched, proj_skills, title_sim, project),
        ))

    # eligible (True > False) first, then by score descending; Python's sort is stable.
    results.sort(key=lambda r: (r.eligible, r.score), reverse=True)
    return results


def rank_bench_for_project(project: Project, consultants: list[Consultant],
                           config: MatchConfig | None = None) -> list[BenchMatch]:
    """The entrypoint a caller uses with an ALREADY-LOADED bench. Never pass a store handle:
    load the bench under a short lock, then score here outside the lock."""
    return rank_consultants(project, consultants, config)


def _bench_reasons(text_sim: float, matched: list[str], proj_skills: list[str],
                   title_sim: float, project: Project) -> list[str]:
    reasons: list[str] = []
    if matched:
        top = ", ".join(matched[:3])
        more = f" +{len(matched) - 3} more" if len(matched) > 3 else ""
        reasons.append(f"Covers {len(matched)}/{len(proj_skills)} required skills ({top}{more})")
    elif proj_skills:
        reasons.append("None of the project's required skills detected on this consultant")
    if text_sim >= 0.7:
        reasons.append("CV closely matches the brief")
    elif text_sim >= 0.4:
        reasons.append("CV generally aligns with the brief")
    if title_sim >= 0.999 and project.title:
        reasons.append(f"Title matches “{project.title}”")
    return reasons[:3]
