"""The Muse (themuse.com) — curated employer jobs. Free, no key.

The Muse's location filter is a global OR (it returns non-Danish jobs too), so we query
the Danish cities and then **filter client-side** to keep only roles actually located in
Denmark.
"""
from __future__ import annotations

import html
import re

import requests

from .base import Job, JobSource

_API = "https://www.themuse.com/api/public/jobs"
_HEADERS = {"User-Agent": "JobFinder/1.0 (personal job search)"}
_DK_LOCATIONS = ["Copenhagen, Denmark", "Aarhus, Denmark", "Odense, Denmark"]
_MAX_PAGES = 6


from .normalize import strip_html as _strip_html   # shared (was a local copy)


def _is_denmark(locations) -> str | None:
    for loc in locations or []:
        if not isinstance(loc, dict):                        # entries can be null / non-dict — skip
            continue
        name = (loc.get("name") or "")
        if "denmark" in name.lower():
            return name
    return None


class TheMuseSource(JobSource):
    name = "themuse"

    def search(self, keywords: str, location: str = "", limit: int = 25,
               remote: bool = False, days: int | None = None) -> list[Job]:
        kw = [w for w in re.split(r"\s+", keywords.lower()) if w]
        jobs: list[Job] = []
        page = 1
        page_count = _MAX_PAGES
        while len(jobs) < limit and page <= min(page_count, _MAX_PAGES):
            try:
                resp = requests.get(_API, params={"location": _DK_LOCATIONS, "page": page},
                                    headers=_HEADERS, timeout=20)
                resp.raise_for_status()
                data = resp.json()
            except Exception as e:
                if page == 1:
                    raise RuntimeError(f"The Muse request failed ({type(e).__name__}).") from e
                break

            results = data.get("results") or []
            page_count = data.get("page_count") or page
            if not results:
                break

            for r in results:
                dk = _is_denmark(r.get("locations") or [])
                if not dk:                       # the location filter is OR-global → enforce DK here
                    continue
                title = (r.get("name") or "").strip()
                desc = _strip_html(r.get("contents", ""))
                if kw and not any(w in f"{title} {desc}".lower() for w in kw):
                    continue
                jobs.append(Job(
                    title=title,
                    company=((r.get("company") or {}).get("name") or "").strip(),
                    location=dk,
                    url=((r.get("refs") or {}).get("landing_page") or "").strip(),
                    description=desc,
                    source="The Muse",
                    posted=(r.get("publication_date") or "")[:10],
                ))
                if len(jobs) >= limit:
                    break
            page += 1
        return jobs
