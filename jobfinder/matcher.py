"""Score and rank job postings against a CV profile.

Hybrid, explainable scoring (0-100):
  * text similarity   — how close the job description is to the whole CV
  * skill overlap     — fraction of the job's required skills present in the CV
  * title match       — does the job title align with the candidate's target titles

Scores are ABSOLUTE (not relative to the batch): a genuinely strong match scores
high whether or not better jobs are present, and a batch of poor matches stays low.
We achieve this by scaling each backend's raw similarity by a "great match" constant
calibrated empirically (e.g. a TF-IDF cosine of ~0.22 between a resume and a posting
is already an excellent textual match).

Default text similarity uses TF-IDF + cosine (scikit-learn): fast, offline, no model
download. If `sentence-transformers` is installed AND semantic=True, we use embeddings
for a more meaning-aware similarity. The app works fully without it.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .cv_parser import CVProfile
from .skills import extract_skills, skill_overlap
from .sources.base import Job

# Weights for the three components (need not sum to 1.0 — we normalise by the
# weights actually used, so a job with no detectable skills isn't penalised or
# inflated; its score is the weighted blend of the remaining signals).
W_TEXT = 0.55
W_SKILLS = 0.30
W_TITLE = 0.15

# "Great match" scaling constants per similarity backend (raw value that maps to 1.0).
_TFIDF_SCALE = 0.22       # TF-IDF cosine ~0.22 == excellent textual match
_JACCARD_SCALE = 0.25
_SEMANTIC_SCALE = 0.55    # MiniLM cosine ~0.55 == excellent semantic match


@dataclass
class MatchConfig:
    semantic: bool = False          # use sentence-transformers if available
    w_text: float = W_TEXT
    w_skills: float = W_SKILLS
    w_title: float = W_TITLE


# ---------------------------------------------------------------------------
# Text similarity backends. Each returns (raw_similarities, scale_constant).
# ---------------------------------------------------------------------------

def _tfidf_similarities(cv_text: str, job_texts: list[str]) -> tuple[list[float], float]:
    """Cosine similarity of each job description to the CV via TF-IDF."""
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity
    except ImportError:
        return _jaccard_similarities(cv_text, job_texts)

    corpus = [cv_text] + job_texts
    try:
        vec = TfidfVectorizer(stop_words="english", ngram_range=(1, 2),
                              sublinear_tf=True, max_features=20000)
        matrix = vec.fit_transform(corpus)
    except ValueError:
        # Empty vocabulary (e.g. all stop words) — fall back gracefully.
        return _jaccard_similarities(cv_text, job_texts)
    sims = cosine_similarity(matrix[0:1], matrix[1:]).ravel()
    return [float(s) for s in sims], _TFIDF_SCALE


def _jaccard_similarities(cv_text: str, job_texts: list[str]) -> tuple[list[float], float]:
    """Dependency-free fallback: token Jaccard similarity."""
    def toks(t: str) -> set[str]:
        return set(re.findall(r"[a-zA-Z][a-zA-Z+#.]{1,}", t.lower()))
    cv = toks(cv_text)
    out = []
    for jt in job_texts:
        j = toks(jt)
        out.append(len(cv & j) / len(cv | j) if cv and j else 0.0)
    return out, _JACCARD_SCALE


def _semantic_similarities(cv_text: str, job_texts: list[str]) -> tuple[list[float], float] | None:
    """Embedding cosine similarity via sentence-transformers, or None if unavailable."""
    try:
        from sentence_transformers import util
    except ImportError:
        return None
    try:
        model = _get_st_model()
        cv_emb = model.encode(cv_text, convert_to_tensor=True, normalize_embeddings=True)
        job_emb = model.encode(job_texts, convert_to_tensor=True, normalize_embeddings=True)
        sims = util.cos_sim(cv_emb, job_emb).cpu().numpy().ravel()
        return [max(0.0, float(s)) for s in sims], _SEMANTIC_SCALE
    except Exception:
        return None


_ST_MODEL = None


def _get_st_model():
    global _ST_MODEL
    if _ST_MODEL is None:
        from sentence_transformers import SentenceTransformer
        _ST_MODEL = SentenceTransformer("all-MiniLM-L6-v2")
    return _ST_MODEL


# ---------------------------------------------------------------------------
# Title matching
# ---------------------------------------------------------------------------

def _title_score(cv_titles: list[str], job_title: str) -> float:
    if not cv_titles or not job_title:
        return 0.0
    jt = job_title.lower()
    best = 0.0
    for t in cv_titles:
        t = t.lower()
        if t in jt:
            best = max(best, 1.0)
        else:
            tw, jw = set(t.split()), set(jt.split())
            if tw:
                best = max(best, len(tw & jw) / len(tw))
    return best


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def rank_jobs(profile: CVProfile, jobs: list[Job], config: MatchConfig | None = None) -> list[Job]:
    """Score every job in-place against the profile and return them sorted best-first."""
    config = config or MatchConfig()
    if not jobs:
        return []

    cv_text = profile.raw_text or " ".join(profile.skills)
    job_texts = [f"{j.title}. {j.description}".strip() for j in jobs]

    # 1) text similarity (absolute, scaled by a "great match" constant)
    result = _semantic_similarities(cv_text, job_texts) if config.semantic else None
    if result is None:
        result = _tfidf_similarities(cv_text, job_texts)
    raw_sims, scale = result
    text_sims = [min(1.0, raw / scale) if scale else 0.0 for raw in raw_sims]

    for job, text, text_sim in zip(jobs, job_texts, text_sims):
        if not job.job_skills:
            job.job_skills = extract_skills(text)

        matched, missing = skill_overlap(profile.skills, job.job_skills)
        job.matched_skills = matched
        job.missing_skills = missing

        title_sim = _title_score(profile.titles, job.title)

        # Blend only the components we actually have signal for, then normalise by
        # the weights used. If a posting has no recognisable skills, skill overlap
        # is genuinely unknown, so we omit it rather than guess (which previously
        # inflated unrelated jobs).
        comps = [
            {"key": "text", "label": "Text similarity", "value": text_sim, "weight": config.w_text},
            {"key": "title", "label": "Title match", "value": title_sim, "weight": config.w_title},
        ]
        if job.job_skills:
            # Recall-oriented: covering the most important ~12 skills of a posting
            # counts as full marks, so a verbose JD listing 30 skills doesn't unfairly
            # tank a strong candidate. Floor of 4 avoids over-rewarding sparse posts.
            denom = max(4, min(len(job.job_skills), 12))
            skill_sim = min(1.0, len(matched) / denom)
            comps.append({"key": "skills", "label": "Skill overlap", "value": skill_sim, "weight": config.w_skills})

        wsum = sum(c["weight"] for c in comps) or 1.0
        raw = sum(c["value"] * c["weight"] for c in comps) / wsum
        job.score = round(max(0.0, min(1.0, raw)) * 100, 1)
        job.explanation = _build_explanation(job, comps, wsum, profile)

    jobs.sort(key=lambda j: j.score, reverse=True)
    return jobs


# ---------------------------------------------------------------------------
# Explanation object — makes the 0-100 transparent ("why this score?")
# ---------------------------------------------------------------------------

def _build_explanation(job: Job, comps: list[dict], wsum: float, profile: CVProfile) -> dict:
    """Decompose the score into per-component contributions that sum to it, plus a
    few plain-English reasons. ``points`` for each component is the share it actually
    contributes (normalised by the weights used), so the components sum to ``score``;
    ``max_points`` is the most that component could contribute given those weights."""
    components = []
    for c in comps:
        share = c["weight"] / wsum            # this component's slice of the 0-100
        components.append({
            "key": c["key"],
            "label": c["label"],
            "strength": round(c["value"] * 100),          # how strong this signal is (0-100)
            "points": round(c["value"] * share * 100, 1),  # points it adds to the final score
            "max_points": round(share * 100, 1),           # ceiling for this component
        })
    return {
        "score": job.score,
        "components": components,
        "reasons": _reasons(job, comps, profile),
        # 'skills' is omitted from scoring when the posting lists no recognisable
        # skills — surface that so a missing component reads as "unknown", not "zero".
        "skills_detected": bool(job.job_skills),
    }


def _reasons(job: Job, comps: list[dict], profile: CVProfile) -> list[str]:
    """Top human-readable reasons, ordered by how much each component drove the score."""
    by_key = {c["key"]: c for c in comps}
    ranked = sorted(comps, key=lambda c: c["value"] * c["weight"], reverse=True)
    reasons: list[str] = []
    for c in ranked:
        v = c["value"]
        if c["key"] == "text":
            if v >= 0.7:
                reasons.append("Closely matches the job description")
            elif v >= 0.4:
                reasons.append("Generally aligns with the job description")
            else:
                reasons.append("Limited textual overlap with the posting")
        elif c["key"] == "skills":
            n = len(job.matched_skills)
            if n:
                top = ", ".join(job.matched_skills[:3])
                more = f" +{n - 3} more" if n > 3 else ""
                reasons.append(f"Matches {n} of your skills ({top}{more})")
            else:
                reasons.append("None of your listed skills were detected in this posting")
        elif c["key"] == "title":
            tgt = profile.titles[0] if profile.titles else ""
            if not tgt:
                continue
            if v >= 0.999:
                reasons.append(f"Title matches your target '{tgt}'")
            elif v > 0:
                reasons.append(f"Title partially matches your target '{tgt}'")
            else:
                continue
    if not by_key.get("skills") and job.job_skills == []:
        reasons.append("No specific skills were detected in this posting")
    return reasons[:3]
