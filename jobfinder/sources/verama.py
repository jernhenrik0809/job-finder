"""Verama (Ework Group's consultant marketplace) — a public, no-login feed of open
**consulting assignments** (fixed-term contracts with a rate, hours/week and start/end dates).

The endpoint is explicitly ``/api/public/...`` and every record is flagged ``public: true`` —
a deliberate open marketplace feed. Nordic-wide (Ework is active in Denmark); every listing is
contract work, so it's a core "job board for a consultant" source.
"""
from __future__ import annotations

import re

import requests

from .base import Job, JobSource
from .normalize import strip_html, iso_date

_API = "https://app.verama.com/api/public/job-requests"
_HEADERS = {"User-Agent": "JobFinder/1.0 (personal job search)", "Accept": "application/json"}


def _is_remote(rv) -> bool:
    """Verama's `remoteness` is an int percentage (0 = onsite); tolerate bool/string too."""
    if isinstance(rv, bool):
        return rv
    if isinstance(rv, (int, float)):
        return rv > 0
    if isinstance(rv, str):
        return rv.strip().lower() in {"yes", "true", "remote", "full", "partial", "hybrid"}
    return False


def _rate(j: dict) -> str:
    rate = j.get("rate")
    rate = rate if isinstance(rate, dict) else {}
    amount = rate.get("maxRate")
    currency = rate.get("currency") or ""
    kind = rate.get("clientRateType") or ""
    try:
        if amount:
            return f"{float(amount):g} {currency} ({kind})".strip()
    except (TypeError, ValueError):
        pass
    return ""


class VeramaSource(JobSource):
    name = "verama"

    def search(self, keywords: str, location: str = "", limit: int = 25,
               remote: bool = False, days: int | None = None) -> list[Job]:
        kw = [w for w in re.split(r"\s+", (keywords or "").lower()) if w]
        loc = (location or "").lower().strip()
        try:
            resp = requests.get(_API, params={"lang": "en", "page": 0, "size": max(limit, 40)},
                                headers=_HEADERS, timeout=20)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            raise RuntimeError(f"Verama request failed ({type(e).__name__}).") from e

        jobs: list[Job] = []
        for j in (data.get("content") if isinstance(data, dict) else None) or []:
            if not isinstance(j, dict):
                continue
            try:                                       # one malformed record must not drop the batch
                title = (j.get("title") or "").strip()
                locs = j.get("locations") if isinstance(j.get("locations"), list) else []
                first_loc = locs[0] if locs and isinstance(locs[0], dict) else {}
                location_str = (first_loc.get("name") or "").strip()
                skills = [s.get("skill", {}).get("name") for s in (j.get("skills") or [])
                          if isinstance(s, dict) and isinstance(s.get("skill"), dict) and s["skill"].get("name")]
                # the list payload has no free-text description — synthesise one from the
                # structured fields (each guarded: a bad optional field omits its bit, not the record)
                bits = []
                lvl = str(j.get("level") or "").strip()
                if lvl:
                    bits.append(f"{lvl.title()} consulting assignment.")
                if j.get("startDate") or j.get("endDate"):
                    bits.append(f"Term: {j.get('startDate') or '?'} – {j.get('endDate') or '?'}.")
                try:
                    if j.get("hoursPerWeek") is not None:
                        bits.append(f"{float(j['hoursPerWeek']):g}h/week.")
                except (TypeError, ValueError):
                    pass
                if skills:
                    bits.append("Skills: " + ", ".join(skills) + ".")
                desc = strip_html(" ".join(bits))
                sid = (j.get("systemId") or "").strip()

                if kw and not any(w in f"{title} {desc}".lower() for w in kw):
                    continue
                if loc and loc not in location_str.lower():
                    continue

                jobs.append(Job(
                    title=title,
                    company="Verama",
                    location=location_str,
                    url=f"https://app.verama.com/en/public/job-requests/{sid}" if sid else "",
                    description=desc,
                    source="Verama (consulting)",
                    posted=iso_date(j.get("createdDate") or j.get("distributionDate") or j.get("publicationDate")),
                    salary=_rate(j),
                    remote=_is_remote(j.get("remoteness")),
                    employment_type="contract",
                ))
            except Exception:
                continue
            if len(jobs) >= limit:
                break
        return jobs
