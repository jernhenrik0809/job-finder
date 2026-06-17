"""Careerjet — large job-search aggregator with a dedicated Danish portal (careerjet.dk,
``da_DK``). Optional, free: needs a free affiliate id (``CAREERJET_AFFID`` / Settings).

Without an affiliate id this source raises a clear error and the app simply skips it.
"""
from __future__ import annotations

import html
import re

import requests

from .base import Job, JobSource
from .. import secrets_store

_API = "https://public.api.careerjet.net/search"
_HEADERS = {"User-Agent": "JobFinder/1.0 (personal job search)"}


def _strip_html(text) -> str:
    text = re.sub(r"<[^>]+>", " ", str(text or ""))
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


class CareerjetSource(JobSource):
    name = "careerjet"

    def __init__(self, affid: str | None = None):
        self.affid = affid or secrets_store.get("careerjet_affid")

    def search(self, keywords: str, location: str = "", limit: int = 25,
               remote: bool = False, days: int | None = None) -> list[Job]:
        if not self.affid:
            raise RuntimeError(
                "Careerjet needs a free affiliate id. Set it in ⚙ Settings (CAREERJET_AFFID) — "
                "get one at https://www.careerjet.com/partners/api ."
            )
        params = {
            "affid": self.affid,
            "locale_code": "da_DK",                      # Danish portal (careerjet.dk)
            "location": location or "Denmark",
            "keywords": keywords or "",
            "sort": "date",
            "pagesize": max(1, min(limit, 100)),
            # required by the API; for a local personal tool these are our own host values
            "user_ip": "127.0.0.1",
            "user_agent": _HEADERS["User-Agent"],
            "url": "http://localhost/jobs",
        }
        try:
            resp = requests.get(_API, params=params, headers=_HEADERS, timeout=25)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            # never echo the exception text — the request URL carries the affiliate id
            raise RuntimeError(f"Careerjet request failed ({type(e).__name__}).") from e

        jobs: list[Job] = []
        for j in (data.get("jobs") or [])[:limit]:
            if not isinstance(j, dict):            # one malformed entry must not drop the batch
                continue
            jobs.append(Job(
                title=(j.get("title") or "").strip(),
                company=(j.get("company") or "").strip(),
                location=(j.get("locations") or "").strip(),
                url=(j.get("url") or "").strip(),
                description=_strip_html(j.get("description", "")),
                source="Careerjet",
                posted=str(j.get("date") or "")[:10],
                salary=(j.get("salary") or "").strip(),
            ))
        return jobs
