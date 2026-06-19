"""Common job model and source interface."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, asdict


@dataclass
class Job:
    title: str
    company: str
    location: str = ""
    url: str = ""
    description: str = ""
    source: str = ""
    # A source-provided UNIQUE id for this posting (e.g. Verama systemId, TED publication-number,
    # HN comment id, Freelancer project id). Used for de-dup so listings from a board that reuses
    # one company name (Verama: every assignment is "Verama") don't collapse into one. Optional —
    # sources that don't set it keep the legacy company+title+location identity unchanged.
    source_uid: str = ""
    posted: str = ""                       # human-readable "posted" string if available
    salary: str = ""
    remote: bool = False
    # "" | full_time | part_time | contract | freelance — drives the "consulting/contract only"
    # filter. Populated by sources that expose it; pure-gig sources set contract/freelance.
    employment_type: str = ""
    job_skills: list[str] = field(default_factory=list)   # skills detected in the posting

    # Filled in by the matcher:
    score: float = 0.0
    matched_skills: list[str] = field(default_factory=list)
    missing_skills: list[str] = field(default_factory=list)
    explanation: dict = field(default_factory=dict)       # why this score (components + reasons)

    @property
    def id(self) -> str:
        """Stable id for de-duplication. Prefer a source-provided unique id (namespaced by
        ``source`` so ids from different boards can't collide); otherwise fall back to the legacy
        company+title+location hash, so sources that don't set ``source_uid`` are unchanged."""
        if self.source_uid:
            key = f"{self.source}|{self.source_uid}".lower()
        else:
            key = f"{self.company}|{self.title}|{self.location}".lower()
        return hashlib.md5(key.encode("utf-8")).hexdigest()[:12]

    def to_dict(self) -> dict:
        d = asdict(self)
        d["id"] = self.id
        return d


class JobSource:
    """Base class for a job source. Subclasses implement :meth:`search`."""

    name: str = "base"

    def search(
        self,
        keywords: str,
        location: str = "",
        limit: int = 25,
        remote: bool = False,
        days: int | None = None,
    ) -> list[Job]:
        raise NotImplementedError
