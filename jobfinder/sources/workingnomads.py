"""Working Nomads — free, public remote-jobs JSON API (no key). Global remote roles.

A single GET returns the whole current feed as a bare JSON array; there are no query params,
so keyword/location filtering is client-side. ``tags`` is a comma-separated string (not a
list) and ``location`` is a free-text remote region. Personal, low-volume use only.
"""
from __future__ import annotations

import html
import re

import requests

from .base import Job, JobSource

_API = "https://www.workingnomads.com/api/exposed_jobs/"
_HEADERS = {"User-Agent": "JobFinder/1.0 (personal job search)"}


def _strip_html(text) -> str:
    text = re.sub(r"<[^>]+>", " ", str(text or ""))
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


class WorkingNomadsSource(JobSource):
    name = "workingnomads"

    def search(self, keywords: str, location: str = "", limit: int = 25,
               remote: bool = False, days: int | None = None) -> list[Job]:
        kw = [w for w in re.split(r"\s+", (keywords or "").lower()) if w]
        loc = (location or "").lower().strip()
        try:
            resp = requests.get(_API, headers=_HEADERS, timeout=20)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            raise RuntimeError(f"Working Nomads request failed ({type(e).__name__}).") from e

        jobs: list[Job] = []
        for j in data if isinstance(data, list) else []:
            if not isinstance(j, dict):
                continue
            title = (j.get("title") or "").strip()
            desc = _strip_html(j.get("description", ""))
            tags = str(j.get("tags") or "")
            category = str(j.get("category_name") or "")
            region = (j.get("location") or "Remote").strip() or "Remote"
            if kw and not any(w in f"{title} {tags} {category} {desc}".lower() for w in kw):
                continue
            if loc and loc not in region.lower():
                continue
            jobs.append(Job(
                title=title,
                company=(j.get("company_name") or "").strip(),
                location=region,
                url=(j.get("url") or "").strip(),
                description=desc,
                source="Working Nomads",
                posted=str(j.get("pub_date") or "")[:10],
                remote=True,
            ))
            if len(jobs) >= limit:
                break
        return jobs
