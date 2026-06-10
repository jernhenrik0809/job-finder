"""Arbeitnow — free job-board API (no key required).

API: https://www.arbeitnow.com/api/job-board-api  (paginated with ?page=)
Returns JSON. European-heavy board, good ToS-friendly fallback / complement.
"""
from __future__ import annotations

import re
import html

import requests

from .base import Job, JobSource

_API = "https://www.arbeitnow.com/api/job-board-api"
_HEADERS = {"User-Agent": "JobFinder/1.0 (personal job search)"}


def _strip_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


class ArbeitnowSource(JobSource):
    name = "arbeitnow"

    def search(self, keywords: str, location: str = "", limit: int = 25,
               remote: bool = False, days: int | None = None) -> list[Job]:
        kw = [w for w in re.split(r"\s+", keywords.lower()) if w]
        loc = location.lower().strip()
        jobs: list[Job] = []
        page = 1
        # Arbeitnow doesn't support server-side keyword search, so we fetch a few
        # pages and filter client-side.
        while len(jobs) < limit and page <= 5:
            try:
                resp = requests.get(_API, params={"page": page}, headers=_HEADERS, timeout=20)
                resp.raise_for_status()
                data = resp.json()
            except Exception as e:
                if page == 1:
                    raise RuntimeError(f"Arbeitnow request failed: {e}") from e
                break

            items = data.get("data", [])
            if not items:
                break

            for item in items:
                title = (item.get("title") or "").strip()
                desc = _strip_html(item.get("description", ""))
                location_str = (item.get("location") or "").strip()
                haystack = f"{title} {desc}".lower()
                if kw and not any(w in haystack for w in kw):
                    continue
                if loc and loc not in location_str.lower() and not item.get("remote"):
                    continue
                jobs.append(Job(
                    title=title,
                    company=(item.get("company_name") or "").strip(),
                    location=location_str or ("Remote" if item.get("remote") else ""),
                    url=item.get("url", ""),
                    description=desc,
                    source="Arbeitnow",
                    posted="",
                    remote=bool(item.get("remote")),
                ))
                if len(jobs) >= limit:
                    break
            page += 1
        return jobs
