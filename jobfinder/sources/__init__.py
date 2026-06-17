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
    if name in ("thehub", "hub"):
        from .thehub import TheHubSource
        return TheHubSource()
    if name in ("themuse", "muse"):
        from .themuse import TheMuseSource
        return TheMuseSource()
    if name in ("jobindex",):
        from .jobindex import JobindexSource
        return JobindexSource()
    if name in ("itjobbank", "it-jobbank"):
        from .itjobbank import ItJobbankSource
        return ItJobbankSource()
    if name in ("hrmanager", "hr-manager", "srl"):
        from .hrmanager import HRManagerSource
        return HRManagerSource()
    if name in ("jobicy",):
        from .jobicy import JobicySource
        return JobicySource()
    if name in ("careerjet",):
        from .careerjet import CareerjetSource
        return CareerjetSource()
    if name in ("stepstonedk", "stepstone", "stepstone-dk"):
        from .stepstonedk import StepStoneDkSource
        return StepStoneDkSource()
    if name in ("remoteok", "remote-ok"):
        from .remoteok import RemoteOKSource
        return RemoteOKSource()
    if name in ("weworkremotely", "wwr"):
        from .weworkremotely import WeWorkRemotelySource
        return WeWorkRemotelySource()
    if name in ("workingnomads", "working-nomads"):
        from .workingnomads import WorkingNomadsSource
        return WorkingNomadsSource()
    if name in ("freelancer", "freelancer.com"):
        from .freelancer import FreelancerSource
        return FreelancerSource()
    raise ValueError(f"Unknown job source: {name!r}")


def available_sources() -> list[str]:
    return ["linkedin", "remotive", "arbeitnow", "thehub", "themuse", "itjobbank",
            "hrmanager", "jobicy", "stepstonedk", "jobindex", "remoteok", "weworkremotely",
            "workingnomads", "adzuna", "jooble", "careerjet", "freelancer", "jsearch"]


__all__ = ["Job", "JobSource", "get_source", "available_sources"]
