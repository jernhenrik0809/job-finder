"""Remotive — free remote-jobs API (no key required).

API: https://remotive.com/api/remote-jobs?search=<q>&limit=<n>
Returns JSON. Great as a reliable, ToS-friendly default/fallback source.
"""
from __future__ import annotations

import re
import html

import requests

from .base import Job, JobSource
from .normalize import strip_html as _strip_html

_API = "https://remotive.com/api/remote-jobs"
_HEADERS = {"User-Agent": "JobFinder/1.0 (personal job search)"}


class RemotiveSource(JobSource):
    name = "remotive"

    def search(self, keywords: str, location: str = "", limit: int = 25,
               remote: bool = False, days: int | None = None) -> list[Job]:
        params = {"search": keywords, "limit": max(limit, 1)}
        try:
            resp = requests.get(_API, params=params, headers=_HEADERS, timeout=20)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            raise RuntimeError(f"Remotive request failed: {e}") from e

        jobs: list[Job] = []
        for item in data.get("jobs", [])[:limit]:
            desc = _strip_html(item.get("description", ""))
            # NB: dict.get(k, default) returns the default only when the key is
            # ABSENT — a present-but-null value yields None, so guard with `or ""`.
            jobs.append(Job(
                title=(item.get("title") or "").strip(),
                company=(item.get("company_name") or "").strip(),
                location=(item.get("candidate_required_location") or "Remote"),
                url=item.get("url") or "",
                description=desc,
                source="Remotive",
                posted=(item.get("publication_date") or "")[:10],
                salary=item.get("salary") or "",
                remote=True,
                employment_type=(item.get("job_type") or "").strip().lower(),   # full_time|contract|freelance|…
            ))
        return jobs
