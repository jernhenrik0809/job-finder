"""Pluggable job sources. Each source implements :class:`JobSource`.

Sources are declared once in the ``_SOURCES`` registry below — a single source of truth for
the name, aliases and (lazily-imported) class of every source. ``get_source`` imports the
module only when a source is actually requested, so an optional source whose dependency is
missing never breaks app startup.
"""
from __future__ import annotations

import importlib
from dataclasses import dataclass, field

from .base import Job, JobSource


@dataclass(frozen=True)
class SourceMeta:
    name: str                       # canonical id (also the UI checkbox value)
    module: str                     # module under jobfinder.sources
    cls: str                        # class name to instantiate
    aliases: tuple = field(default_factory=tuple)


# Order is cosmetic. Aliases preserve the historical accept-list so existing configs/tests
# keep working. ``ats`` covers the Greenhouse/Lever/Ashby public board APIs.
_SOURCES: tuple[SourceMeta, ...] = (
    SourceMeta("linkedin", "linkedin", "LinkedInSource", ("li",)),
    SourceMeta("remotive", "remotive", "RemotiveSource", ("remote",)),
    SourceMeta("arbeitnow", "arbeitnow", "ArbeitnowSource", ("arbeit",)),
    SourceMeta("thehub", "thehub", "TheHubSource", ("hub",)),
    SourceMeta("themuse", "themuse", "TheMuseSource", ("muse",)),
    SourceMeta("itjobbank", "itjobbank", "ItJobbankSource", ("it-jobbank",)),
    SourceMeta("hrmanager", "hrmanager", "HRManagerSource", ("hr-manager", "srl")),
    SourceMeta("jobicy", "jobicy", "JobicySource"),
    SourceMeta("stepstonedk", "stepstonedk", "StepStoneDkSource", ("stepstone", "stepstone-dk")),
    SourceMeta("jobindex", "jobindex", "JobindexSource"),
    SourceMeta("remoteok", "remoteok", "RemoteOKSource", ("remote-ok",)),
    SourceMeta("weworkremotely", "weworkremotely", "WeWorkRemotelySource", ("wwr",)),
    SourceMeta("workingnomads", "workingnomads", "WorkingNomadsSource", ("working-nomads",)),
    SourceMeta("ats", "ats", "ATSSource", ("greenhouse", "lever", "ashby")),
    SourceMeta("adzuna", "adzuna", "AdzunaSource"),
    SourceMeta("jooble", "jooble", "JoobleSource"),
    SourceMeta("careerjet", "careerjet", "CareerjetSource"),
    SourceMeta("freelancer", "freelancer", "FreelancerSource", ("freelancer.com",)),
    SourceMeta("jsearch", "jsearch", "JSearchSource"),
)

_BY_NAME: dict[str, SourceMeta] = {}
for _m in _SOURCES:
    for _n in (_m.name, *_m.aliases):
        _BY_NAME[_n] = _m


def get_source(name: str) -> JobSource:
    meta = _BY_NAME.get((name or "").lower())
    if meta is None:
        raise ValueError(f"Unknown job source: {name!r}")
    module = importlib.import_module(f".{meta.module}", __name__)   # lazy: optional deps stay optional
    return getattr(module, meta.cls)()


def available_sources() -> list[str]:
    return [m.name for m in _SOURCES]


__all__ = ["Job", "JobSource", "SourceMeta", "get_source", "available_sources"]
