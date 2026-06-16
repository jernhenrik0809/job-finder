"""Pipeline analytics — derived entirely from the persisted applications, offline.

Turns a multi-week job search into a funnel, response/conversion metrics, and a short
list of follow-up nudges. No telemetry; everything is computed on demand from the
Application event timelines the user already created.
"""
from __future__ import annotations

import time

from .applications import Application, STATUSES

# Stages that count as a positive employer response (got past "applied").
_RESPONSE = {"screening", "interview", "offer"}
_DAY = 86400.0


def _statuses_ever(app: Application) -> set[str]:
    """Every lifecycle status this application has ever held (from its event timeline)."""
    seen = {"saved", app.status}                  # everyone enters the pipeline at 'saved'
    for ev in app.events:
        if ev.get("type") == "status":
            # detail is "<from> → <to>"
            to = ev.get("detail", "").split("→")[-1].strip()
            if to in STATUSES:
                seen.add(to)
    return seen


def _first_response_ts(app: Application) -> float | None:
    for ev in app.events:
        if ev.get("type") == "status":
            to = ev.get("detail", "").split("→")[-1].strip()
            if to in _RESPONSE:
                return ev.get("ts")
    return None


def _has_letter(app: Application, seen: set[str]) -> bool:
    return bool(app.body) or bool({"drafting", "ready"} & seen) or app.generator in ("template", "llm")


def compute_insights(apps: list[Application], now: float | None = None) -> dict:
    now = now if now is not None else time.time()
    total = len(apps)
    by_status = {s: 0 for s in STATUSES}
    for a in apps:
        if a.status in by_status:
            by_status[a.status] += 1

    drafted = applied = interviewing = offers = responded = 0
    ttr_samples: list[float] = []
    by_source: dict[str, int] = {}
    nudges: list[dict] = []

    for a in apps:
        seen = _statuses_ever(a)
        reached_applied = (a.applied_at is not None) or ("applied" in seen) or bool(_RESPONSE & seen)
        reached_interviewing = bool(seen & {"screening", "interview", "offer"})
        reached_offer = "offer" in seen

        if _has_letter(a, seen):
            drafted += 1
        if reached_applied:
            applied += 1
            src = a.job_source or "other"
            by_source[src] = by_source.get(src, 0) + 1
        if reached_interviewing:
            interviewing += 1
            responded += 1
        if reached_offer:
            offers += 1

        fr = _first_response_ts(a)
        if a.applied_at and fr and fr >= a.applied_at:
            ttr_samples.append(fr - a.applied_at)

        # --- follow-up nudges (surfaced when the app is open; no background scheduler) ---
        ref = a.applied_at or a.updated or a.created
        age_days = (now - ref) / _DAY if ref else 0
        if a.status == "applied" and age_days >= 7:
            nudges.append({"id": a.id, "title": a.job_title, "company": a.company,
                           "message": f"Applied {int(age_days)} days ago — consider a follow-up.",
                           "days": int(age_days)})
        elif a.status in ("ready", "drafting") and age_days >= 3:
            nudges.append({"id": a.id, "title": a.job_title, "company": a.company,
                           "message": f"Drafted {int(age_days)} days ago — ready to send.",
                           "days": int(age_days)})
    nudges.sort(key=lambda n: n["days"], reverse=True)

    funnel = [
        {"stage": "saved", "count": total},
        {"stage": "drafted", "count": drafted},
        {"stage": "applied", "count": applied},
        {"stage": "interviewing", "count": interviewing},
        {"stage": "offer", "count": offers},
    ]

    avg_ttr = round((sum(ttr_samples) / len(ttr_samples)) / _DAY, 1) if ttr_samples else None
    response_rate = round(responded / applied * 100) if applied else 0

    by_source_list = sorted(
        ({"source": s, "applied": n} for s, n in by_source.items()),
        key=lambda d: d["applied"], reverse=True,
    )

    # applications created per week, last 8 weeks (oldest → newest)
    weeks = 8
    buckets = [0] * weeks
    for a in apps:
        if not a.created:
            continue
        idx = int((now - a.created) // (7 * _DAY))
        if 0 <= idx < weeks:
            buckets[weeks - 1 - idx] += 1
    over_time = [{"label": ("now" if i == weeks - 1 else f"-{weeks - 1 - i}w"), "count": c}
                 for i, c in enumerate(buckets)]

    return {
        "total": total,
        "by_status": by_status,
        "funnel": funnel,
        "response_rate": response_rate,
        "offers": offers,
        "avg_time_to_response_days": avg_ttr,
        "by_source": by_source_list,
        "over_time": over_time,
        "nudges": nudges[:10],
    }
