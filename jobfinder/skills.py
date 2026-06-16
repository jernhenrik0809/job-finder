"""Skill extraction from free text using a curated skills dictionary.

We deliberately avoid heavy ML here so the app runs fully offline on any laptop.
A dictionary + word-boundary regex matching is fast, predictable and explainable.
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

_SKILLS_FILE = Path(__file__).parent / "data" / "skills.txt"

# A handful of aliases so different spellings collapse to one canonical skill.
_ALIASES = {
    "golang": "go",
    "react.js": "react",
    "node": "node.js",
    "nodejs": "node.js",
    "postgres": "postgresql",
    "k8s": "kubernetes",
    "sklearn": "scikit-learn",
    "ml": "machine learning",
    "ai": "artificial intelligence",
    "js": "javascript",
    "ts": "typescript",
    "gcp": "google cloud",
    "aws": "aws",
    "vue.js": "vue",
    "angular.js": "angular",
    "angularjs": "angular",
}


@lru_cache(maxsize=1)
def load_skills() -> list[str]:
    """Return the curated skills list (lower-cased, de-duplicated, longest-first)."""
    skills: list[str] = []
    seen: set[str] = set()
    for raw in _SKILLS_FILE.read_text(encoding="utf-8").splitlines():
        line = raw.strip().lower()
        if not line or line.startswith("#"):
            continue
        if line not in seen:
            seen.add(line)
            skills.append(line)
    # Longest first so multi-word phrases win over their sub-words during matching.
    skills.sort(key=len, reverse=True)
    return skills


@lru_cache(maxsize=1)
def _compiled_patterns() -> list[tuple[str, re.Pattern]]:
    """Pre-compile a word-boundary regex for every skill (cached for speed)."""
    patterns = []
    for skill in load_skills():
        # Escape regex special chars (c++, c#, .net, etc.) then allow flexible
        # boundaries that also work for tokens containing +, # and dots.
        escaped = re.escape(skill)
        if len(skill) == 1:
            # Single-letter languages ("c", "r") are highly ambiguous. Also exclude
            # parenthesis/copyright adjacency so "(c)" copyright text, "(r)" etc. and
            # bullet markers don't masquerade as the C/R language.
            pattern = re.compile(rf"(?<![A-Za-z0-9+#.(©®]){escaped}(?![A-Za-z0-9+#)])", re.IGNORECASE)
        else:
            pattern = re.compile(rf"(?<![A-Za-z0-9+#.]){escaped}(?![A-Za-z0-9+#])", re.IGNORECASE)
        patterns.append((skill, pattern))
    return patterns


def _canonical(skill: str) -> str:
    return _ALIASES.get(skill, skill)


def canonical(skill: str) -> str:
    """Public: normalise a skill string to its canonical form (lower, alias-resolved)."""
    return _canonical(skill.strip().lower())


@lru_cache(maxsize=1)
def non_technical_skills() -> frozenset[str]:
    """Soft skills + human languages from the dictionary (canonicalised).

    These are excluded from the cover-letter "unsupported skill claim" guardrail: they
    appear constantly in ordinary prose ("strong leadership", "clear communication") and
    aren't credentials you fact-check against a CV, so flagging them is noise.
    """
    out: set[str] = set()
    excluding = False
    for raw in _SKILLS_FILE.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line.startswith("#"):
            low = line.lower()
            if line.startswith("# ---"):
                excluding = ("soft skills" in low) or ("languages (human)" in low)
            continue
        if line and excluding:
            out.add(_canonical(line.lower()))
    return frozenset(out)


def skill_spans(text: str) -> list[tuple[str, int, int]]:
    """Every (canonical_skill, start, end) mention in ``text`` (all matches, not just
    the first) — lets callers inspect the surrounding context of a mention."""
    if not text:
        return []
    lowered = text.lower()
    spans: list[tuple[str, int, int]] = []
    for skill, pattern in _compiled_patterns():
        for m in pattern.finditer(lowered):
            spans.append((_canonical(skill), m.start(), m.end()))
    return spans


def extract_skills(text: str) -> list[str]:
    """Extract the set of known skills mentioned in ``text``.

    Returns canonical skill names, ordered by first appearance in the text so the
    most prominent (usually top-of-CV) skills come first.
    """
    if not text:
        return []
    lowered = text.lower()
    found: dict[str, int] = {}  # canonical skill -> first position
    for skill, pattern in _compiled_patterns():
        m = pattern.search(lowered)
        if m:
            canon = _canonical(skill)
            pos = m.start()
            if canon not in found or pos < found[canon]:
                found[canon] = pos
    return [s for s, _ in sorted(found.items(), key=lambda kv: kv[1])]


def skill_overlap(cv_skills: list[str], job_skills: list[str]) -> tuple[list[str], list[str]]:
    """Return (matched, missing) skills given a CV's skills and a job's skills.

    Both sides are canonicalised so a CV that lists "golang"/"k8s" matches a job's
    "go"/"kubernetes" (otherwise the candidate's real skills look like gaps)."""
    cv_set = {_canonical(s.lower()) for s in cv_skills}
    matched, missing = [], []
    for s in job_skills:
        (matched if _canonical(s.lower()) in cv_set else missing).append(s)
    return matched, missing
