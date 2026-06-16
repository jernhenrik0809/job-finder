"""Application = the durable pipeline item (a job you're actively pursuing).

Promotes the former 'draft' into a tracked Application: a lifecycle status, an immutable
event timeline, free-text notes, the generated cover letter as its current artifact, and a
snapshot of the job context (+ the cv_id used) so the letter can be regenerated later
without re-running a search. This is the retention core — it turns a one-shot draft buffer
into a multi-week campaign tracker.
"""
from __future__ import annotations

import secrets
import time
from dataclasses import dataclass, field, asdict

# Canonical lifecycle, in pipeline order. The board renders one column per status.
STATUSES = [
    "saved", "drafting", "ready", "applied",
    "screening", "interview", "offer", "rejected", "withdrawn",
]
TERMINAL = {"rejected", "withdrawn"}

# Suggested "next" moves the UI surfaces as quick buttons. The server allows any move to a
# *known* status (a personal tracker — drag anywhere); this just guides the common path.
SUGGESTED_NEXT = {
    "saved": ["drafting", "ready", "withdrawn"],
    "drafting": ["ready", "applied", "withdrawn"],
    "ready": ["applied", "withdrawn"],
    "applied": ["screening", "interview", "offer", "rejected"],
    "screening": ["interview", "offer", "rejected"],
    "interview": ["offer", "rejected"],
    "offer": ["rejected", "withdrawn"],
    "rejected": ["applied"],
    "withdrawn": ["saved"],
}


@dataclass
class Application:
    job_title: str
    company: str = ""
    job_url: str = ""
    job_source: str = ""
    location: str = ""
    score: float = 0.0
    status: str = "saved"
    cv_id: str = ""                  # the CV this application is matched to (for regeneration)
    subject: str = ""               # current cover-letter artifact
    body: str = ""
    generator: str = ""             # "" | "template" | "llm"
    gen_note: str = ""              # generator warning (placeholder / fallback)
    notes: str = ""                 # user's free-text notes
    job: dict = field(default_factory=dict)         # snapshot: description, matched/missing skills
    events: list = field(default_factory=list)      # immutable [{ts, type, detail}]
    applied_at: float | None = None
    created: float = 0.0
    updated: float = 0.0
    id: str = field(default_factory=lambda: secrets.token_urlsafe(8))

    def to_dict(self) -> dict:
        return asdict(self)


def record_event(app: Application, etype: str, detail: str = "") -> None:
    app.events.append({"ts": time.time(), "type": etype, "detail": detail})
    app.updated = time.time()


def new_application(job: dict, cv_id: str = "", status: str = "saved") -> Application:
    now = time.time()
    app = Application(
        job_title=(job.get("title") or "this role"),
        company=(job.get("company") or ""),
        job_url=(job.get("url") or ""),
        job_source=(job.get("source") or ""),
        location=(job.get("location") or ""),
        score=float(job.get("score") or 0),
        status=status if status in STATUSES else "saved",
        cv_id=cv_id,
        job={
            "description": (job.get("description") or "")[:6000],
            "matched_skills": job.get("matched_skills") or [],
            "missing_skills": job.get("missing_skills") or [],
        },
        created=now, updated=now,
    )
    record_event(app, "created", f"Added to pipeline as “{app.status}”")
    return app


def set_status(app: Application, to: str) -> None:
    """Move to a new lifecycle status (validated). Logs an event; stamps applied_at once."""
    if to not in STATUSES:
        raise ValueError(f"Unknown status: {to!r}")
    if to == app.status:
        return
    frm = app.status
    app.status = to
    if to == "applied" and app.applied_at is None:
        app.applied_at = time.time()
    record_event(app, "status", f"{frm} → {to}")


def attach_letter(app: Application, subject: str, body: str, generator: str, note: str = "") -> None:
    """Store a generated cover letter as the application's current artifact."""
    app.subject = subject
    app.body = body
    app.generator = generator
    app.gen_note = note
    if app.status in ("saved", "drafting"):
        app.status = "ready"
    record_event(app, "draft", f"Cover letter generated ({generator})")


def job_snapshot(app: Application) -> dict:
    """Reconstruct a job dict (for regeneration) from the stored snapshot + card fields."""
    j = dict(app.job or {})
    j.setdefault("title", app.job_title)
    j.setdefault("company", app.company)
    j.setdefault("url", app.job_url)
    j.setdefault("source", app.job_source)
    j.setdefault("score", app.score)
    return j
