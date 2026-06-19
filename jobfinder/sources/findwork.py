"""Findwork.dev — a curated tech job board with a clean REST API. Optional, free: needs a
free API token (``FINDWORK_TOKEN`` / Settings — get one at findwork.dev/account). The token
rides in the ``Authorization`` header (never the URL), and ``remote`` / ``location`` are
honoured server-side, so a Denmark-based developer can pull remote / EU-eligible roles.

Without a token this source raises a clear error and the app simply skips it.
"""
from __future__ import annotations

import requests

from .base import Job, JobSource
from .. import secrets_store
from .normalize import strip_html, iso_date

_API = "https://findwork.dev/api/jobs/"
_HEADERS = {"User-Agent": "JobFinder/1.0 (personal job search)", "Accept": "application/json"}


def _emp_type(t) -> str:
    t = str(t or "").strip().lower()
    if "freelance" in t:
        return "freelance"
    if "contract" in t:
        return "contract"
    if "part" in t:
        return "part_time"
    if "full" in t:
        return "full_time"
    return ""


class FindworkSource(JobSource):
    name = "findwork"

    def __init__(self, token: str | None = None):
        self.token = token or secrets_store.get("findwork_token")

    def search(self, keywords: str, location: str = "", limit: int = 25,
               remote: bool = False, days: int | None = None) -> list[Job]:
        if not self.token:
            raise RuntimeError(
                "Findwork needs a free API token. Set it in ⚙ Settings (FINDWORK_TOKEN) — "
                "get one at https://findwork.dev/account ."
            )
        params: dict[str, str] = {"sort_by": "date"}
        if keywords:
            params["search"] = keywords
        if location:
            params["location"] = location
        if remote:
            params["remote"] = "true"
        headers = {**_HEADERS, "Authorization": f"Token {self.token}"}
        try:
            resp = requests.get(_API, params=params, headers=headers, timeout=25)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            # never echo the exception text — the token rides in a request header
            raise RuntimeError(f"Findwork request failed ({type(e).__name__}).") from e

        jobs: list[Job] = []
        for j in (data.get("results") if isinstance(data, dict) else None) or []:
            if not isinstance(j, dict):                # one malformed entry must not drop the batch
                continue
            try:
                kws = [k for k in (j.get("keywords") or []) if isinstance(k, str)]
                desc = strip_html(j.get("text"))
                if kws:
                    desc = (desc + "  Skills: " + ", ".join(kws) + ".").strip()
                jobs.append(Job(
                    title=str(j.get("role") or "").strip(),
                    company=str(j.get("company_name") or "").strip(),
                    location=str(j.get("location") or "").strip() or (
                        "Remote" if j.get("remote") else ""),
                    url=str(j.get("url") or "").strip(),
                    description=desc,
                    source="Findwork",
                    posted=iso_date(j.get("date_posted")),
                    remote=bool(j.get("remote")),
                    employment_type=_emp_type(j.get("employment_type")),
                ))
            except Exception:
                continue
            if len(jobs) >= limit:
                break
        return jobs
