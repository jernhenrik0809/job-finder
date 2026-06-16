"""Jooble — free job-search API that covers Denmark (and most countries).

Needs a free API key (one POST endpoint, no per-country setup):

    https://jooble.org/api/about   →  set JOOBLE_API_KEY

Scope it to Denmark by searching with a Danish location (e.g. "Denmark", "Copenhagen").
Without a key this source raises a clear error and the app simply skips it.
"""
from __future__ import annotations

import html
import re

import requests

from .base import Job, JobSource
from ..config import settings

_HEADERS = {"User-Agent": "JobFinder/1.0 (personal job search)", "Content-Type": "application/json"}


def _strip_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def _s(v) -> str:
    """Coerce any API value to a stripped string — guards null AND wrong types
    (e.g. a numeric salary, which would crash .strip())."""
    return "" if v is None else str(v).strip()


class JoobleSource(JobSource):
    name = "jooble"

    def __init__(self, api_key: str | None = None, default_location: str = "Denmark"):
        self.api_key = api_key or settings.jooble_key
        self.default_location = default_location

    def search(self, keywords: str, location: str = "", limit: int = 25,
               remote: bool = False, days: int | None = None) -> list[Job]:
        if not self.api_key:
            raise RuntimeError(
                "Jooble needs a free API key. Set JOOBLE_API_KEY (get it at https://jooble.org/api/about)."
            )
        body = {
            "keywords": keywords,
            # default to Denmark so this source stays Denmark-relevant when no location is given
            "location": location or self.default_location,
            "page": "1",
        }
        try:
            resp = requests.post(f"https://jooble.org/api/{self.api_key}", json=body, headers=_HEADERS, timeout=25)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            # Never echo the exception text: it embeds the request URL, which carries the
            # API key in its path (the message reaches /api/search warnings).
            status = getattr(getattr(e, "response", None), "status_code", None)
            raise RuntimeError(
                f"Jooble request failed ({type(e).__name__}" + (f", HTTP {status}" if status else "") + ")"
            ) from e

        jobs: list[Job] = []
        for item in (data.get("jobs") or [])[:limit]:
            jobs.append(Job(
                title=_s(item.get("title")),
                company=_s(item.get("company")),
                location=_s(item.get("location")),
                url=_s(item.get("link")),
                description=_strip_html(item.get("snippet")),
                source="Jooble",
                posted=_s(item.get("updated"))[:10],
                salary=_s(item.get("salary")),
                remote=remote,
            ))
        return jobs
