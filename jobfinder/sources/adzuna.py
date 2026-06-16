"""Adzuna — free, ToS-friendly job aggregator with a dedicated Denmark endpoint.

Adzuna has a per-country API; we default to Denmark (``dk``), overridable via
``JOBFINDER_ADZUNA_COUNTRY``. Needs a free ``app_id`` + ``app_key``:

    https://developer.adzuna.com/   →  set ADZUNA_APP_ID and ADZUNA_APP_KEY

Without credentials this source raises a clear error and the app simply skips it.
"""
from __future__ import annotations

import html
import re

import requests

from .base import Job, JobSource
from ..config import settings

_HEADERS = {"User-Agent": "JobFinder/1.0 (personal job search)"}


def _strip_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


class AdzunaSource(JobSource):
    name = "adzuna"

    def __init__(self, app_id: str | None = None, app_key: str | None = None, country: str | None = None):
        self.app_id = app_id or settings.adzuna_app_id
        self.app_key = app_key or settings.adzuna_app_key
        self.country = (country or settings.adzuna_country or "dk").lower()

    def search(self, keywords: str, location: str = "", limit: int = 25,
               remote: bool = False, days: int | None = None) -> list[Job]:
        if not (self.app_id and self.app_key):
            raise RuntimeError(
                "Adzuna needs a free app_id + app_key. Set ADZUNA_APP_ID and ADZUNA_APP_KEY "
                "(get them at https://developer.adzuna.com/)."
            )
        url = f"https://api.adzuna.com/v1/api/jobs/{self.country}/search/1"
        params = {
            "app_id": self.app_id,
            "app_key": self.app_key,
            "results_per_page": max(1, min(limit, 50)),
            "what": keywords,
            "content-type": "application/json",
        }
        if location:
            params["where"] = location
        if remote:
            params["what_or"] = (keywords + " remote").strip()
        if days:
            params["max_days_old"] = days
        try:
            resp = requests.get(url, params=params, headers=_HEADERS, timeout=25)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            raise RuntimeError(f"Adzuna request failed: {e}") from e

        jobs: list[Job] = []
        for item in (data.get("results") or [])[:limit]:
            company = ((item.get("company") or {}).get("display_name") or "").strip()
            loc = ((item.get("location") or {}).get("display_name") or "").strip()
            salary = ""
            lo, hi = item.get("salary_min"), item.get("salary_max")
            if lo and hi:
                salary = f"{int(lo):,}–{int(hi):,}"
            elif lo:
                salary = f"from {int(lo):,}"
            jobs.append(Job(
                title=(item.get("title") or "").strip(),
                company=company,
                location=loc,
                url=item.get("redirect_url") or "",
                description=_strip_html(item.get("description")),
                source="Adzuna",
                posted=(item.get("created") or "")[:10],
                salary=salary,
                remote=remote,
            ))
        return jobs
