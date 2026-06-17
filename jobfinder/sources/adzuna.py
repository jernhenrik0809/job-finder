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
from .normalize import strip_html as _strip_html
from ..config import settings
from .. import secrets_store

_HEADERS = {"User-Agent": "JobFinder/1.0 (personal job search)"}


def _s(v) -> str:
    """Coerce any API value to a stripped string — guards null AND wrong types."""
    return "" if v is None else str(v).strip()


def _money(v) -> str:
    """Format a salary figure with thousands separators.

    Adzuna returns these as JSON numbers, but a proxy/cache could serialize them as
    a decimal string ("500000.0"); ``int(float(v))`` handles both, and a bad value
    yields "" rather than crashing the whole source.
    """
    try:
        return f"{int(float(v)):,}"
    except (TypeError, ValueError):
        return ""


class AdzunaSource(JobSource):
    name = "adzuna"

    def __init__(self, app_id: str | None = None, app_key: str | None = None, country: str | None = None):
        self.app_id = app_id or secrets_store.get("adzuna_app_id")
        self.app_key = app_key or secrets_store.get("adzuna_app_key")
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
            # Never echo the exception text: it embeds the request URL, which carries
            # app_id/app_key as query params (the message reaches /api/search warnings).
            status = getattr(getattr(e, "response", None), "status_code", None)
            raise RuntimeError(
                f"Adzuna request failed ({type(e).__name__}" + (f", HTTP {status}" if status else "") + ")"
            ) from e

        jobs: list[Job] = []
        for item in (data.get("results") or [])[:limit]:
            company = _s((item.get("company") or {}).get("display_name"))
            loc = _s((item.get("location") or {}).get("display_name"))
            salary = ""
            lo, hi = _money(item.get("salary_min")), _money(item.get("salary_max"))
            if lo and hi:
                salary = f"{lo}–{hi}"
            elif lo:
                salary = f"from {lo}"
            jobs.append(Job(
                title=_s(item.get("title")),
                company=company,
                location=loc,
                url=_s(item.get("redirect_url")),
                description=_strip_html(item.get("description")),
                source="Adzuna",
                posted=_s(item.get("created"))[:10],
                salary=salary,
                remote=remote,
            ))
        return jobs
