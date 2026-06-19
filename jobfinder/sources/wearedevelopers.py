"""WeAreDevelopers (Vienna) — a large pan-European / DACH tech job board. Public, no-key JSON
API (the feed behind their site): ~hundreds of thousands of listings with a ``remote`` flag and
``location``, so a Denmark-based developer can filter to remote / EU-eligible roles.

Mostly permanent dev jobs (not a gig marketplace), but high-volume EU coverage. Server-side
keyword params are ignored, so keywords are filtered client-side (same pattern as Jobicy).
"""
from __future__ import annotations

import re

import requests

from .base import Job, JobSource
from .normalize import strip_html, iso_date

_API = "https://wad-api.wearedevelopers.com/api/v2/jobs/search"
_HEADERS = {"User-Agent": "JobFinder/1.0 (personal job search)", "Accept": "application/json"}


def _emp_type(job_type) -> str:
    jt = str(job_type or "").strip().lower()           # coerce: a non-string must not drop the record
    if "freelance" in jt:
        return "freelance"
    if "contract" in jt:
        return "contract"
    return ""


class WeAreDevelopersSource(JobSource):
    name = "wearedevelopers"

    def search(self, keywords: str, location: str = "", limit: int = 25,
               remote: bool = False, days: int | None = None) -> list[Job]:
        kw = [w for w in re.split(r"\s+", (keywords or "").lower()) if w]
        loc = (location or "").lower().strip()
        try:
            resp = requests.get(_API, params={"per_page": max(1, min(limit * 2, 100)), "page": 1},
                                headers=_HEADERS, timeout=20)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            raise RuntimeError(f"WeAreDevelopers request failed ({type(e).__name__}).") from e

        jobs: list[Job] = []
        for j in (data.get("data") if isinstance(data, dict) else None) or []:
            if not isinstance(j, dict):
                continue
            try:
                title = (j.get("title") or "").strip()
                skills = [s for s in (j.get("skills") or []) if isinstance(s, str)]
                levels = [s for s in (j.get("seniorities") or []) if isinstance(s, str)]
                bits = []
                if levels:
                    bits.append("Seniority: " + ", ".join(levels) + ".")
                if skills:
                    bits.append("Skills: " + ", ".join(skills) + ".")
                desc = strip_html(" ".join(bits))
                location_str = (j.get("location") or "").strip()
                if kw and not any(w in f"{title} {desc}".lower() for w in kw):
                    continue
                if loc and loc not in location_str.lower():
                    continue
                jid, slug = str(j.get("id") or "").strip(), (j.get("slug") or "").strip()
                jobs.append(Job(
                    title=title,
                    company=(j.get("company_name") or "").strip(),
                    location=location_str or ("Remote" if j.get("remote") else ""),
                    url=f"https://www.wearedevelopers.com/en/jobs/{jid}/{slug}" if jid else "",
                    description=desc,
                    source="WeAreDevelopers",
                    posted=iso_date(j.get("last_published_at")),
                    salary=(j.get("salary") or "").strip(),
                    remote=bool(j.get("remote")),
                    employment_type=_emp_type(j.get("job_type")),
                ))
            except Exception:
                continue
            if len(jobs) >= limit:
                break
        return jobs
