"""Jobicy — free, public remote-jobs JSON API (no key). Denmark-eligible remote roles.

Mirrors the Remotive/Arbeitnow pattern. We use ``geo=denmark`` to scope to Denmark-eligible
remote work and filter keywords client-side.
"""
from __future__ import annotations

import html
import re

import requests

from .base import Job, JobSource

_API = "https://jobicy.com/api/v2/remote-jobs"
_HEADERS = {"User-Agent": "JobFinder/1.0 (personal job search)"}


from .normalize import strip_html as _strip_html   # shared (was a local copy)


class JobicySource(JobSource):
    name = "jobicy"

    def search(self, keywords: str, location: str = "", limit: int = 25,
               remote: bool = False, days: int | None = None) -> list[Job]:
        kw = [w for w in re.split(r"\s+", keywords.lower()) if w]
        try:
            resp = requests.get(_API, params={"count": 50, "geo": "denmark"},
                                headers=_HEADERS, timeout=20)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            raise RuntimeError(f"Jobicy request failed ({type(e).__name__}).") from e

        jobs: list[Job] = []
        for j in data.get("jobs") or []:
            if not isinstance(j, dict):            # one malformed entry must not drop the batch
                continue
            title = (j.get("jobTitle") or "").strip()
            desc = _strip_html(j.get("jobDescription", ""))
            if kw and not any(w in f"{title} {desc}".lower() for w in kw):
                continue
            geo = j.get("jobGeo") or "Remote"
            jtypes = [str(t).strip().lower() for t in (j.get("jobType") or []) if isinstance(t, str)]
            emp = "contract" if "contract" in jtypes else ("freelance" if "freelance" in jtypes else "")
            jobs.append(Job(
                title=title,
                company=(j.get("companyName") or "").strip(),
                location=geo,
                url=(j.get("url") or "").strip(),
                description=desc,
                source="Jobicy",
                posted=str(j.get("pubDate") or "")[:10],
                remote=True,
                employment_type=emp,
            ))
            if len(jobs) >= limit:
                break
        return jobs
