"""Opportunity = a project the house is PURSUING — the durable bid record.

The consulting-house counterpart to ``applications.Application`` (a job-seeker's tracked
application). An Opportunity captures the project snapshot, who is staffed on the bid (per-
consultant commercial lines), the generated proposal artifact + its last QA result, a lifecycle
status, and an **append-only event timeline** — the audit trail that makes "a human reviewed and
sent this" a durable, defensible record rather than a verbal promise.

Idempotency: an opportunity ingested from a job board carries ``source`` + ``source_uid`` so the
same posting re-surfaced by a later sweep updates the existing row instead of duplicating it
(the store exposes ``get_opportunity_by_posting``).
"""
from __future__ import annotations

import secrets
import time
from dataclasses import dataclass, field, asdict, fields

# Lifecycle, in pipeline order. ``submitted`` is a MANUAL-only transition (a human submits) and
# ``no_bid`` records a deliberate decision not to pursue.
STATUSES = [
    "lead", "qualifying", "proposal_drafting", "proposal_ready",
    "submitted", "won", "lost", "no_bid",
]
TERMINAL = {"won", "lost", "no_bid"}

SUGGESTED_NEXT = {
    "lead": ["qualifying", "no_bid"],
    "qualifying": ["proposal_drafting", "no_bid"],
    "proposal_drafting": ["proposal_ready", "no_bid"],
    "proposal_ready": ["submitted", "no_bid"],
    "submitted": ["won", "lost"],
    "won": [],
    "lost": ["qualifying"],
    "no_bid": ["qualifying"],
}


def _to_float(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


@dataclass
class Opportunity:
    title: str
    kind: str = "posting"            # posting | warm
    source: str = ""
    source_uid: str = ""             # with ``source``, the idempotency key for an ingested posting
    url: str = ""
    location: str = ""
    description: str = ""
    skills: list[str] = field(default_factory=list)
    client_id: str = ""              # for warm leads (Phase 3)
    rate_ceiling: float | None = None
    currency: str = ""
    start_date: str = ""
    status: str = "lead"
    # per-consultant bid lines: [{consultant_id, consultant_name, cost_rate, sell_rate, currency}]
    staffed: list[dict] = field(default_factory=list)
    # the current proposal artifact + its last QA findings (so the UI can re-show the gate result)
    proposal_subject: str = ""
    proposal_body: str = ""
    proposal_generator: str = ""     # "" | template | llm
    qa: list[dict] = field(default_factory=list)
    notes: str = ""
    events: list = field(default_factory=list)        # append-only audit: [{ts, type, detail, meta}]
    created: float = 0.0
    updated: float = 0.0
    id: str = field(default_factory=lambda: secrets.token_urlsafe(8))

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Opportunity":
        allowed = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in allowed})


def record_event(opp: Opportunity, etype: str, detail: str = "", meta: dict | None = None) -> None:
    """Append an immutable audit event and bump ``updated``. Never overwrites prior events —
    this is the defensible trail of generate / QA / export / status actions."""
    opp.events.append({"ts": time.time(), "type": etype, "detail": detail, "meta": meta or {}})
    opp.updated = time.time()


def margin_of(line: dict) -> float | None:
    """sell − cost for a bid line, but ONLY within one currency (never a wrong cross-FX number)."""
    cost, sell = _to_float(line.get("cost_rate")), _to_float(line.get("sell_rate"))
    if cost is None or sell is None:
        return None
    return round(sell - cost, 2)


def new_opportunity(project: dict, kind: str = "posting", status: str = "lead") -> Opportunity:
    now = time.time()
    opp = Opportunity(
        title=(project.get("title") or "Untitled project"),
        kind=kind if kind in ("posting", "warm") else "posting",
        source=(project.get("source") or ""),
        source_uid=(project.get("source_uid") or project.get("id") or ""),
        url=(project.get("url") or ""),
        location=(project.get("location") or ""),
        description=(project.get("description") or "")[:8000],
        skills=[s for s in (project.get("skills") or []) if isinstance(s, str)],
        rate_ceiling=_to_float(project.get("rate_ceiling")),
        currency=(project.get("currency") or ""),
        start_date=(project.get("start_date") or ""),
        status=status if status in STATUSES else "lead",
        created=now, updated=now,
    )
    record_event(opp, "created", f"Opportunity added as “{opp.status}”",
                 {"source": opp.source, "source_uid": opp.source_uid})
    return opp


def set_status(opp: Opportunity, to: str) -> None:
    if to not in STATUSES:
        raise ValueError(f"Unknown status: {to!r}")
    if to == opp.status:
        return
    frm = opp.status
    opp.status = to
    record_event(opp, "status", f"{frm} → {to}")


def set_staffing(opp: Opportunity, lines: list[dict]) -> None:
    """Replace the staffed bid lines (each {consultant_id, consultant_name, cost_rate, sell_rate,
    currency}); records an audit event naming who is now on the bid."""
    clean: list[dict] = []
    for ln in lines or []:
        if not isinstance(ln, dict) or not ln.get("consultant_id"):
            continue
        clean.append({
            "consultant_id": str(ln.get("consultant_id")),
            "consultant_name": str(ln.get("consultant_name") or ""),
            "cost_rate": _to_float(ln.get("cost_rate")),
            "sell_rate": _to_float(ln.get("sell_rate")),
            "currency": str(ln.get("currency") or ""),
        })
    opp.staffed = clean
    names = ", ".join(l["consultant_name"] or l["consultant_id"] for l in clean) or "(none)"
    record_event(opp, "staffed", f"Staffed: {names}",
                 {"consultant_ids": [l["consultant_id"] for l in clean]})


def attach_proposal(opp: Opportunity, subject: str, body: str, generator: str,
                    qa: list[dict], blocking: bool) -> None:
    """Store a generated proposal as the opportunity's current artifact + log the audit event
    (generator, whether the QA gate blocked, and which finding types fired)."""
    opp.proposal_subject = subject
    opp.proposal_body = body
    opp.proposal_generator = generator
    opp.qa = qa or []
    if opp.status in ("lead", "qualifying", "proposal_drafting"):
        opp.status = "proposal_ready" if not blocking else "proposal_drafting"
    record_event(opp, "proposal_generated", f"Proposal drafted ({generator})",
                 {"generator": generator, "blocking": bool(blocking),
                  "qa_types": sorted({f.get("type") for f in (qa or []) if f.get("type")})})


def record_export(opp: Opportunity) -> None:
    """Log that a human exported the proposal (the 'a human took it from here' acknowledgement)."""
    record_event(opp, "exported", "Proposal exported by the operator")
