"""Pluggable job sources. Each source implements :class:`JobSource`."""
from __future__ import annotations

from .base import Job, JobSource

# Registry of available sources is built lazily to avoid import-time failures
# when an optional source's dependency is missing.

def get_source(name: str) -> JobSource:
    name = (name or "").lower()
    if name in ("linkedin", "li"):
        from .linkedin import LinkedInSource
        return LinkedInSource()
    if name in ("remotive", "remote"):
        from .remotive import RemotiveSource
        return RemotiveSource()
    if name in ("arbeitnow", "arbeit"):
        from .arbeitnow import ArbeitnowSource
        return ArbeitnowSource()
    if name in ("jsearch",):
        from .jsearch import JSearchSource
        return JSearchSource()
    if name in ("adzuna",):
        from .adzuna import AdzunaSource
        return AdzunaSource()
    if name in ("jooble",):
        from .jooble import JoobleSource
        return JoobleSource()
    raise ValueError(f"Unknown job source: {name!r}")


def available_sources() -> list[str]:
    return ["linkedin", "remotive", "arbeitnow", "adzuna", "jooble", "jsearch"]


__all__ = ["Job", "JobSource", "get_source", "available_sources"]
