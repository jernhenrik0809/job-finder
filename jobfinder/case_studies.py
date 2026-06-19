"""CaseStudy = a grounded, attributable proof record — the house's delivered engagements.

The proposal "Relevant proof" section (playbook §2.4) needs quantified, *verifiable* outcomes the
document engine can render WITHOUT fabricating. A `CaseStudy` is that source: each one is tied to
the consultant(s) who delivered it and carries structured, per-metric outcomes — so a number on a
bid traces to a real engagement, not an LLM's imagination.

A **disclosure** flag (public / anonymized_only / confidential) plus **reference_consent** control
what may go into a client-facing document: confidential studies are never rendered, anonymized-only
ones drop the client name, and a reference may only be named when consent is recorded.
"""
from __future__ import annotations

import secrets
import time
from dataclasses import dataclass, field, asdict, fields

# What the house may disclose about this engagement in a client-facing document.
DISCLOSURE = ("public", "anonymized_only", "confidential")


def _clean_outcomes(outcomes) -> list[dict]:
    """Keep well-formed quantified outcomes: {metric, value, unit?}. A metric is required; value/
    unit are coerced to strings. Malformed entries are dropped (never crash a render)."""
    out: list[dict] = []
    for o in outcomes or []:
        if not isinstance(o, dict):
            continue
        metric = str(o.get("metric") or "").strip()
        if not metric:
            continue
        out.append({"metric": metric, "value": str(o.get("value") or "").strip(),
                    "unit": str(o.get("unit") or "").strip()})
    return out


@dataclass
class CaseStudy:
    title: str
    client_name: str = ""              # the client; may be hidden per ``disclosure``
    client_anonymized: str = ""        # neutral descriptor when anonymized (e.g. "a Danish pension provider")
    sector: str = ""
    summary: str = ""                  # what was delivered (the prose)
    outcomes: list[dict] = field(default_factory=list)   # [{metric, value, unit}] — quantified proof
    skills: list[str] = field(default_factory=list)      # technologies/skills demonstrated
    consultant_ids: list[str] = field(default_factory=list)   # who delivered it (attribution)
    disclosure: str = "confidential"   # public | anonymized_only | confidential (default safest)
    reference_contact: str = ""        # internal — never client-facing
    reference_consent: bool = False    # may we name this client as a reference?
    start_date: str = ""
    end_date: str = ""
    notes: str = ""                    # internal
    created: float = 0.0
    updated: float = 0.0
    id: str = field(default_factory=lambda: secrets.token_urlsafe(8))

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "CaseStudy":
        allowed = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in allowed})

    def display_client(self) -> str:
        """The client label safe to show given the disclosure setting (never the real name when
        anonymized/confidential)."""
        if self.disclosure == "public":
            return (self.client_name or self.client_anonymized or "").strip()
        return (self.client_anonymized or "a client").strip()

    def is_renderable(self) -> bool:
        """Confidential case studies must never appear in a client-facing document."""
        return self.disclosure in ("public", "anonymized_only")


def new_case_study(title: str, **kw) -> CaseStudy:
    now = time.time()
    if "outcomes" in kw:
        kw["outcomes"] = _clean_outcomes(kw["outcomes"])
    disclosure = kw.get("disclosure")
    if disclosure is not None and str(disclosure).strip().lower() not in DISCLOSURE:
        kw.pop("disclosure")           # ignore an unknown disclosure → keep the safe default
    return CaseStudy(title=(title or "").strip() or "Untitled engagement",
                     created=now, updated=now, **kw)
