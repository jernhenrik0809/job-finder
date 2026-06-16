"""Résumé tailoring — surface the CV content most relevant to a specific job.

This is selection + reordering of the candidate's *real* CV, never fabrication. Each
ranked bullet carries its source text (provenance), so the output is always traceable to
something the candidate actually wrote. The optional Claude pass only *rephrases* an
existing bullet to emphasise the role — it is instructed never to add a fact not present
in that bullet, and the original is always shown alongside for the user to verify.
"""
from __future__ import annotations

import re

from .config import settings
from .cv_parser import CVProfile
from .drafts import llm_available
from .matcher import _tfidf_similarities
from .privacy import redact_pii
from .skills import extract_skills, skill_overlap

_BULLET_PREFIX = re.compile(r"^\s*[-•*–—>·∙]+\s*")
_CONTACT_HINT = ("phone", "email", "e-mail", "tel:", "mobile", "linkedin", "github", "address")
# Achievement bullets usually open with an action verb; skill lists ("Python, Django, …") don't.
_ACTION_VERBS = {
    "built", "led", "designed", "developed", "created", "managed", "implemented", "delivered",
    "drove", "launched", "shipped", "improved", "reduced", "increased", "mentored", "owned",
    "architected", "scaled", "automated", "migrated", "optimized", "optimised", "deployed",
    "founded", "spearheaded", "established", "coordinated", "directed", "engineered",
    "analyzed", "analysed", "researched", "wrote", "maintained", "supported", "collaborated",
}


def _segment_bullets(text: str) -> list[str]:
    """Pull résumé bullets / accomplishment lines out of raw CV text."""
    out: list[str] = []
    seen: set[str] = set()
    for raw in (text or "").splitlines():
        line = _BULLET_PREFIX.sub("", raw).strip()
        low = line.lower()
        if len(line) < 25 or " " not in line:
            continue
        if line.isupper():                      # section header (SKILLS, EXPERIENCE)
            continue
        if "@" in line or low.startswith(_CONTACT_HINT):
            continue
        # Skip comma-separated keyword lists (a skills line, not an accomplishment bullet):
        # 3+ short comma parts AND the line doesn't open with an action verb (which would
        # mark it as a real achievement like "Built APIs, shipped features, led reviews").
        parts = [p.strip() for p in line.split(",") if p.strip()]
        first_word = line.split()[0].lower().strip(":.,")
        if (len(parts) >= 3 and (sum(len(p.split()) for p in parts) / len(parts)) <= 2
                and first_word not in _ACTION_VERBS):
            continue
        if line not in seen:
            seen.add(line)
            out.append(line)
    return out


def _job_text(job: dict) -> str:
    return (f"{job.get('title', '')}. {job.get('description', '')} "
            f"{' '.join(job.get('matched_skills') or [])}").strip()


def tailor_resume(profile: CVProfile, job: dict, top_n: int = 8) -> dict:
    """Offline tailoring: rank the candidate's own bullets by relevance to the job."""
    job_text = _job_text(job)
    bullets = _segment_bullets(profile.raw_text or "")

    ranked: list[dict] = []
    if bullets and job_text:
        sims, scale = _tfidf_similarities(job_text, bullets)
        order = sorted(range(len(bullets)), key=lambda i: sims[i], reverse=True)
        for rank, i in enumerate(order[:top_n]):
            ranked.append({
                "text": bullets[i],                 # the source line — this is the provenance
                "score": round(min(1.0, (sims[i] / scale) if scale else 0) * 100),
                "source_index": i,
            })

    matched = job.get("matched_skills")
    if not matched:
        matched, _ = skill_overlap(profile.skills, extract_skills(job_text))
    missing = job.get("missing_skills") or []

    return {
        "emphasize_skills": list(matched)[:12],
        "gaps": list(missing)[:8],
        "bullets": ranked,
        "generator": "template",
    }


_REWRITE_SYSTEM = (
    "You tailor résumé bullet points to a specific job. For each numbered original bullet, "
    "rewrite it to emphasise what THIS job is looking for. CRITICAL: use ONLY the facts present "
    "in that original bullet — never invent metrics, technologies, employers, scope, or outcomes. "
    "Keep it to one concise line. Return exactly one rewritten line per original, in order, each "
    "prefixed with its number and a period (e.g. '1. ...'). No commentary, no extra lines."
)


def _rewrite_bullets_llm(bullets: list[dict], job: dict, model: str, redact: bool = False) -> None:
    """Optionally rephrase the ranked bullets via Claude (in place). Best-effort."""
    if not bullets:
        return
    import anthropic
    client = anthropic.Anthropic()
    _scrub = redact_pii if redact else (lambda t: t)
    numbered = "\n".join(f"{i + 1}. {_scrub(b['text'])}" for i, b in enumerate(bullets))
    user = (
        f"Job title: {job.get('title', 'this role')}\n"
        f"Company: {job.get('company', '')}\n"
        f"What the job wants: {', '.join(job.get('matched_skills') or []) or '(infer from the title)'}\n\n"
        f"Original bullets:\n{numbered}"
    )
    resp = client.messages.create(
        model=model, max_tokens=1200,
        system=[{"type": "text", "text": _REWRITE_SYSTEM}],
        messages=[{"role": "user", "content": user}],
    )
    text = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")
    by_index: dict[int, str] = {}
    for line in text.splitlines():
        m = re.match(r"\s*(\d+)\s*[.)]\s*(.+)", line)
        if m:
            by_index[int(m.group(1)) - 1] = m.group(2).strip()
    for i, b in enumerate(bullets):
        if i in by_index and by_index[i]:
            b["rewritten"] = by_index[i]


def generate_tailoring(profile: CVProfile, job: dict, use_llm: bool = True, top_n: int = 8,
                       redact_pii: bool = False) -> dict:
    """Offline tailoring, plus an optional grounded Claude rewrite of the ranked bullets."""
    result = tailor_resume(profile, job, top_n=top_n)
    if use_llm and llm_available() and result["bullets"]:
        try:
            _rewrite_bullets_llm(result["bullets"], job, settings.model, redact=redact_pii)
            result["generator"] = "llm"
        except Exception as e:
            result["note"] = f"Claude rewrite unavailable ({type(e).__name__}); showing the ranked originals."
    return result
