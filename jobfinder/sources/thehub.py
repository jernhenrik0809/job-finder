"""The Hub (thehub.io) — Nordic startup/scale-up jobs, strong Denmark coverage.

Free, no key: the public JSON API the site's own frontend uses. We filter to Denmark
with ``countryCode=DK`` and paginate politely (the server caps the page size at 15).
"""
from __future__ import annotations

import html
import re

import requests

from .base import Job, JobSource

_API = "https://thehub.io/api/jobs"
_HEADERS = {"User-Agent": "JobFinder/1.0 (personal job search)"}
_MAX_PAGES = 6


def _strip_html(text) -> str:
    text = re.sub(r"<[^>]+>", " ", str(text or ""))          # str() guards a non-string field
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


class TheHubSource(JobSource):
    name = "thehub"

    def search(self, keywords: str, location: str = "", limit: int = 25,
               remote: bool = False, days: int | None = None) -> list[Job]:
        kw = [w for w in re.split(r"\s+", keywords.lower()) if w]
        loc = location.lower().strip()
        jobs: list[Job] = []
        page = 1
        pages = _MAX_PAGES
        # The API has no reliable server-side keyword search, so we pull DK jobs and
        # filter client-side (like the Arbeitnow source).
        while len(jobs) < limit and page <= min(pages, _MAX_PAGES):
            try:
                resp = requests.get(_API, params={"countryCode": "DK", "page": page},
                                    headers=_HEADERS, timeout=20)
                resp.raise_for_status()
                data = resp.json()
            except Exception as e:
                if page == 1:
                    raise RuntimeError(f"The Hub request failed ({type(e).__name__}).") from e
                break

            docs = data.get("docs") or []
            pages = data.get("pages") or page
            if not docs:
                break

            for d in docs:
                title = (d.get("title") or "").strip()
                desc = _strip_html(d.get("description", ""))
                loc_obj = d.get("location") or {}
                location_str = (loc_obj.get("address") or loc_obj.get("locality") or "Denmark").strip()
                is_remote = bool(d.get("isRemote"))
                if remote and not is_remote:
                    continue
                if kw and not any(w in f"{title} {desc}".lower() for w in kw):
                    continue
                if loc and loc not in location_str.lower() and not is_remote:
                    continue
                jobs.append(Job(
                    title=title,
                    company=((d.get("company") or {}).get("name") or "").strip(),
                    location=location_str or ("Remote" if is_remote else ""),
                    url=(d.get("absoluteJobUrl") or "").strip(),
                    description=desc,
                    source="The Hub",
                    posted=(d.get("publishedAt") or "")[:10],
                    remote=is_remote,
                ))
                if len(jobs) >= limit:
                    break
            page += 1
        return jobs
