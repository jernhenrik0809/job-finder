"""High-level orchestration: turn a CV + search settings into ranked job matches."""
from __future__ import annotations

from dataclasses import dataclass, field

from .cv_parser import CVProfile, build_profile, extract_text, extract_text_from_bytes
from .matcher import MatchConfig, rank_jobs
from .sources import get_source
from .sources.base import Job


@dataclass
class SearchSettings:
    keywords: str = ""
    location: str = ""
    sources: list[str] = field(default_factory=lambda: ["linkedin"])
    limit_per_source: int = 25
    remote: bool = False
    days: int | None = None          # only jobs posted within N days
    semantic: bool = False           # use embeddings if available
    min_score: float = 0.0           # filter out jobs below this match score


@dataclass
class SearchResult:
    jobs: list[Job]
    profile: CVProfile
    warnings: list[str] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)


def profile_from_file(path: str) -> CVProfile:
    return build_profile(extract_text(path))


def profile_from_bytes(data: bytes, filename: str) -> CVProfile:
    return build_profile(extract_text_from_bytes(data, filename))


def find_jobs(profile: CVProfile, settings: SearchSettings) -> SearchResult:
    """Search the chosen sources, de-duplicate, score against the CV, and rank."""
    keywords = settings.keywords.strip() or profile.suggested_keywords or (
        profile.titles[0] if profile.titles else (profile.skills[0] if profile.skills else "")
    )

    all_jobs: list[Job] = []
    warnings: list[str] = []
    counts: dict[str, int] = {}

    for source_name in settings.sources:
        try:
            source = get_source(source_name)
        except ValueError as e:
            warnings.append(str(e))
            continue
        try:
            jobs = source.search(
                keywords=keywords,
                location=settings.location,
                limit=settings.limit_per_source,
                remote=settings.remote,
                days=settings.days,
            )
            counts[source_name] = len(jobs)
            all_jobs.extend(jobs)
            warn = getattr(source, "last_warning", None)
            if warn:
                warnings.append(warn)
        except Exception as e:  # one bad source shouldn't kill the search
            warnings.append(f"{source_name}: {e}")
            counts[source_name] = 0

    # De-duplicate across sources by stable id.
    deduped: dict[str, Job] = {}
    for job in all_jobs:
        deduped.setdefault(job.id, job)
    jobs = list(deduped.values())

    # Score & rank.
    rank_jobs(profile, jobs, MatchConfig(semantic=settings.semantic))

    if settings.min_score > 0:
        jobs = [j for j in jobs if j.score >= settings.min_score]

    return SearchResult(jobs=jobs, profile=profile, warnings=warnings, counts=counts)
