"""RemoteOK — free, public remote-jobs JSON API (no key). Global remote roles.

The endpoint returns a JSON array whose **first element is a legal/metadata object**, not a
job — it is skipped. RemoteOK's terms ask that we link back to the original RemoteOK job URL
and credit "Remote OK" as the source (no logo reuse): this tool only ever links out to the
original ``job.url`` and labels the source "Remote OK", so that attribution is satisfied.
Keyword filtering is client-side (the ``tags=`` query param does not filter server-side).
"""
from __future__ import annotations

import html
import re
from datetime import datetime, timezone

import requests

from .base import Job, JobSource

_API = "https://remoteok.com/api"
# RemoteOK blocks default script User-Agents; a realistic browser UA is required to get 200.
_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
    "Accept": "application/json",
}


from .normalize import strip_html as _strip_html   # shared (was a local copy)


def _posted(j: dict) -> str:
    """Posted date from the ISO ``date`` string, falling back to the ``epoch`` int."""
    d = j.get("date")
    if isinstance(d, str) and d:
        return d[:10]
    ep = j.get("epoch")
    try:
        return datetime.fromtimestamp(int(ep) / (1000 if int(ep) > 10_000_000_000 else 1),
                                      tz=timezone.utc).date().isoformat()
    except (TypeError, ValueError, OverflowError, OSError):
        return ""


def _salary(j: dict) -> str:
    lo, hi = j.get("salary_min") or 0, j.get("salary_max") or 0
    try:
        lo, hi = int(lo), int(hi)
    except (TypeError, ValueError):
        return ""
    if hi:
        return f"{lo:,}–{hi:,} USD" if lo else f"up to {hi:,} USD"
    return ""


class RemoteOKSource(JobSource):
    name = "remoteok"

    def search(self, keywords: str, location: str = "", limit: int = 25,
               remote: bool = False, days: int | None = None) -> list[Job]:
        kw = [w for w in re.split(r"\s+", (keywords or "").lower()) if w]
        try:
            resp = requests.get(_API, headers=_HEADERS, timeout=20)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            raise RuntimeError(f"RemoteOK request failed ({type(e).__name__}).") from e

        jobs: list[Job] = []
        for j in data if isinstance(data, list) else []:
            if not isinstance(j, dict) or "position" not in j:   # skip the legal/metadata head
                continue
            title = (j.get("position") or "").strip()
            desc = _strip_html(j.get("description", ""))
            tags = " ".join(t for t in (j.get("tags") or []) if isinstance(t, str))
            if kw and not any(w in f"{title} {tags} {desc}".lower() for w in kw):
                continue
            jobs.append(Job(
                title=title,
                company=(j.get("company") or "").strip(),
                location=(j.get("location") or "Remote").strip() or "Remote",
                url=(j.get("url") or j.get("apply_url") or "").strip(),
                description=desc,
                source="Remote OK",
                posted=_posted(j),
                salary=_salary(j),
                remote=True,
            ))
            if len(jobs) >= limit:
                break
        return jobs
