"""Freelancer.com — active short-term project listings (freelance gigs), via the official
Projects REST API. Optional, free: needs a free static OAuth token (``FREELANCER_TOKEN`` /
Settings) from a Freelancer developer account.

Projects are client-posted gigs (no employer/company name), inherently remote. Without a
token this source raises a clear error and the app simply skips it. The token rides in a
request header (not the URL), but error text is still sanitised to the exception type name.
"""
from __future__ import annotations

import html
import re
from datetime import datetime, timezone

import requests

from .base import Job, JobSource
from .. import secrets_store

_API = "https://www.freelancer.com/api/projects/0.1/projects/active/"


from .normalize import strip_html as _strip_html   # shared (was a local copy)


def _posted(value) -> str:
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc).date().isoformat()
    except (TypeError, ValueError, OverflowError, OSError):
        return ""


def _salary(p: dict) -> str:
    budget = p.get("budget")
    budget = budget if isinstance(budget, dict) else {}
    currency = p.get("currency")
    code = (currency or {}).get("code") if isinstance(currency, dict) else ""
    lo, hi = budget.get("minimum"), budget.get("maximum")
    try:
        lo = float(lo) if lo is not None else None
        hi = float(hi) if hi is not None else None
    except (TypeError, ValueError):
        return ""
    if lo and hi:
        return f"{lo:g}–{hi:g} {code}".strip()
    if hi:
        return f"up to {hi:g} {code}".strip()
    if lo:
        return f"from {lo:g} {code}".strip()
    return ""


class FreelancerSource(JobSource):
    name = "freelancer"

    def __init__(self, token: str | None = None):
        self.token = token or secrets_store.get("freelancer_token")

    def search(self, keywords: str, location: str = "", limit: int = 25,
               remote: bool = False, days: int | None = None) -> list[Job]:
        if not self.token:
            raise RuntimeError(
                "Freelancer needs a free OAuth token. Set it in ⚙ Settings (FREELANCER_TOKEN) — "
                "get one at https://www.freelancer.com/api/docs ."
            )
        headers = {"Freelancer-OAuth-V1": self.token, "User-Agent": "JobFinder/1.0 (personal job search)"}
        params = {
            "query": keywords or "",
            "limit": max(1, min(limit, 50)),
            "offset": 0,
            "job_details": "true",          # include jobs[] (skills)
            "full_description": "true",
        }
        try:
            resp = requests.get(_API, params=params, headers=headers, timeout=25)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            # never echo the exception text — keep the bearer token out of any message
            raise RuntimeError(f"Freelancer request failed ({type(e).__name__}).") from e

        projects = ((data.get("result") or {}).get("projects")
                    if isinstance(data, dict) else None) or []
        jobs: list[Job] = []
        for p in projects:
            if not isinstance(p, dict):
                continue
            desc = _strip_html(p.get("description") or p.get("preview_description") or "")
            skills = [j.get("name") for j in (p.get("jobs") or [])
                      if isinstance(j, dict) and j.get("name")]
            if skills:
                desc = f"{desc}  Skills: {', '.join(skills)}".strip()
            seo = (p.get("seo_url") or "").strip()
            jobs.append(Job(
                title=(p.get("title") or "").strip(),
                company="",                                  # gigs are client-posted, no employer
                location="Remote",
                url=f"https://www.freelancer.com/projects/{seo}" if seo else "",
                description=desc,
                source="Freelancer",
                source_uid=(str(p.get("id") or "").strip() or seo),   # project id (or slug) — every gig is company=""
                posted=_posted(p.get("submitdate") or p.get("time_submitted")),
                salary=_salary(p),
                remote=True,
                employment_type="freelance",                 # every Freelancer project is a gig
            ))
            if len(jobs) >= limit:
                break
        return jobs
