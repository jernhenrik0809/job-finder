"""Consultant = a member of the house's BENCH — the person we match against incoming
postings and put forward in a proposal.

This is the consulting-house counterpart to a job-seeker's single ``CVProfile``: a stable,
durable record for *many* people, carrying the fields a *bid* needs (skills + availability +
commercials + engagement terms) that a one-off profile never had. A Consultant links to a
parsed ``CVProfile`` via ``cv_id`` for its skills / raw text, so onboarding reuses the
existing upload → ``build_profile`` path.

Field shapes here are deliberately frozen up front — they are cheap to capture now and
ruinous to backfill once the bench fills up (engagement terms, provenance, commercials).
GDPR consent/retention machinery is intentionally NOT built (owner decision); only a cheap
free-text ``consent_note`` and a one-field ``data_origin`` provenance are kept, because
provenance is free to record now and impossible to reconstruct later.
"""
from __future__ import annotations

import secrets
import time
from dataclasses import dataclass, field, asdict, fields

# How the house engages this person — drives who can be sub-contracted and the cost/sell split.
ENGAGEMENT_TYPES = ("employee", "associate", "subcontractor")
# Where the CV/data came from — cheap provenance, captured once, impossible to backfill later.
DATA_ORIGINS = ("direct_from_subject", "third_party", "public_source")
STATUSES = ("active", "inactive")


@dataclass
class Consultant:
    name: str
    cv_id: str = ""                       # link to a parsed CVProfile (skills / raw_text for matching)
    title: str = ""                       # primary role headline
    skills: list[str] = field(default_factory=list)
    seniority: str = ""                   # "" | junior | mid | senior | lead
    languages: list[str] = field(default_factory=list)

    # --- availability (a freshness TTL lands later; record the update stamp now) ---
    available_from: str = ""              # ISO date; "" = available now / unknown
    available_until: str = ""             # ISO date; "" = open-ended
    hours_per_week: int | None = None
    availability_updated: float = 0.0

    # --- commercials (per-consultant DEFAULTS; a bid line on an Opportunity can override) ---
    cost_rate: float | None = None        # what this person costs the house
    sell_rate: float | None = None        # default rate we would bill a client
    currency: str = ""                    # ISO 4217 ("DKK"/"EUR"); margin is compared within-currency only

    # --- engagement + rights ---
    engagement_type: str = "associate"    # employee | associate | subcontractor
    right_to_present: bool = True          # may we put this person forward in a bid?

    # --- provenance (kept despite GDPR de-prioritization: free now, impossible to reconstruct) ---
    data_origin: str = "direct_from_subject"
    source_detail: str = ""               # e.g. "uploaded by Anna" / "LinkedIn export"
    consent_note: str = ""                # optional free-text hygiene only — no enforcement

    # --- eligibility / placement ---
    clearance: str = ""                   # free-text e.g. "EU work permit", "security clearance"
    certifications: list[str] = field(default_factory=list)
    location: str = ""
    remote_ok: bool = True

    status: str = "active"                # active | inactive (inactive = excluded from matching)
    raw_text: str = ""                    # CV text for matching (falls back to skills if empty)
    notes: str = ""
    created: float = 0.0
    updated: float = 0.0
    id: str = field(default_factory=lambda: secrets.token_urlsafe(8))

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Consultant":
        """Reconstruct from a stored dict, ignoring unknown keys so a later schema change
        (a renamed/added field in another build) never crashes the read path."""
        allowed = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in allowed})

    def match_text(self) -> str:
        """Text used to vector-match this consultant against a posting (CV text, else skills)."""
        return (self.raw_text or "").strip() or " ".join(self.skills)


def new_consultant(name: str, **kw) -> Consultant:
    now = time.time()
    c = Consultant(name=name, created=now, updated=now, **kw)
    if c.availability_updated == 0.0:
        c.availability_updated = now
    return c


def consultant_from_profile(profile, cv_id: str = "", **overrides) -> Consultant:
    """Onboard a bench member from an already-parsed CVProfile (reuses the upload path).
    ``cv_id`` is the key the profile is stored under (kept so the CV can be re-read later)."""
    base = dict(
        name=(getattr(profile, "name", "") or "Unnamed consultant"),
        cv_id=cv_id,
        title=(list(getattr(profile, "titles", []) or [""]) or [""])[0],
        skills=list(getattr(profile, "skills", []) or []),
        seniority=(getattr(profile, "seniority", "") or ""),
        raw_text=(getattr(profile, "raw_text", "") or ""),
        location=(getattr(profile, "location", "") or ""),
    )
    base.update(overrides)
    return new_consultant(**base)
