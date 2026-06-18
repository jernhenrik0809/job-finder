"""Saved searches — a reusable query that resurfaces what's *new* since you last checked.

A SavedSearch stores the search settings plus the set of job ids it has already seen.
Running it again diffs the fresh results against that set; anything not seen before is a
"new match". No background scheduler — searches run on demand (or via a catch-up sweep
when you open the app), which keeps the app a single, off-friendly local process.
"""
from __future__ import annotations

import secrets
import time
from dataclasses import dataclass, field, asdict, fields

_MAX_SEEN = 1000   # bound the remembered-id set so it can't grow without limit


@dataclass
class SavedSearch:
    name: str
    cv_id: str = ""
    keywords: str = ""
    location: str = ""
    sources: list = field(default_factory=list)
    limit_per_source: int = 25
    remote: bool = False
    days: int | None = None
    semantic: bool = False
    min_score: float = 0.0
    gigs_only: bool = False                          # "consulting/contract only"
    seen_ids: list = field(default_factory=list)     # job ids already surfaced
    new_count: int = 0                               # new matches at last run, not yet viewed
    last_run: float | None = None
    created: float = 0.0
    id: str = field(default_factory=lambda: secrets.token_urlsafe(8))

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "SavedSearch":
        allowed = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in allowed})

    def summary(self) -> dict:
        return {"id": self.id, "name": self.name, "keywords": self.keywords,
                "location": self.location, "sources": self.sources,
                "new_count": self.new_count, "last_run": self.last_run}


def new_saved_search(name: str, req: dict) -> SavedSearch:
    now = time.time()
    return SavedSearch(
        name=(name or "Saved search").strip()[:80],
        cv_id=req.get("cv_id") or "",
        keywords=req.get("keywords") or "",
        location=req.get("location") or "",
        sources=list(req.get("sources") or []),
        limit_per_source=int(req.get("limit_per_source") or 25),
        remote=bool(req.get("remote")),
        days=req.get("days"),
        semantic=bool(req.get("semantic")),
        min_score=float(req.get("min_score") or 0),
        gigs_only=bool(req.get("gigs_only")),
        created=now,
    )


def register_run(search: SavedSearch, job_ids: list[str]) -> list[str]:
    """Record a run: return the ids not seen before, update seen-set, bump new_count.

    new_count reflects matches found that the user hasn't viewed yet, so it is *not*
    reset here — the caller resets it via mark_seen() once the user looks at the results.
    """
    seen = set(search.seen_ids)
    new_ids = [jid for jid in job_ids if jid and jid not in seen]
    if new_ids:
        search.seen_ids = (search.seen_ids + new_ids)[-_MAX_SEEN:]
        search.new_count += len(new_ids)
    search.last_run = time.time()
    return new_ids


def mark_seen(search: SavedSearch) -> None:
    search.new_count = 0
