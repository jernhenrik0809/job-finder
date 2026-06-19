"""EU TED (Tenders Electronic Daily) — Danish public-sector IT & business **consultancy
tenders** (limited-time projects you bid on). The canonical, ToS-clean open-data API that
subsumes udbud.dk + Mercell.

These are procurement RFPs (you bid as a supplier), not employee jobs, so the source is
labelled "EU TED (tender)" and is opt-in. CPV 72 = IT services, 79 = business/management
consultancy; scoped to place-of-performance Denmark.
"""
from __future__ import annotations

import re
from datetime import date, timedelta

import requests

from .base import Job, JobSource
from .normalize import strip_html, iso_date

_API = "https://api.ted.europa.eu/v3/notices/search"
_HEADERS = {"User-Agent": "JobFinder/1.0 (personal job search)",
            "Content-Type": "application/json", "Accept": "application/json"}
# title-proc carries the clean (usually Danish) procurement title; notice-title is a messy
# multilingual map that often lacks eng/dan, so prefer title-proc.
_FIELDS = ["publication-number", "title-proc", "notice-title", "buyer-name",
           "publication-date", "deadline-receipt-request"]


def _leaf(v) -> str:
    """A single language value — str, a list (take first), or a nested {value/#text} dict."""
    if isinstance(v, list):
        return str(v[0]) if v else ""
    if isinstance(v, dict):
        for tk in ("value", "#text", "text", "label"):
            if v.get(tk):
                return str(v[tk])
        return ""
    return str(v) if v is not None else ""


def _lang(value) -> str:
    """A TED multilingual field — a dict of lang→(str|list|dict). Prefer English, then Danish."""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return _leaf(value)
    if isinstance(value, dict):
        for key in ("eng", "dan", "ENG", "DAN"):
            if value.get(key):
                return _leaf(value[key])
        for v in value.values():                       # fall back to any language present
            if v:
                return _leaf(v)
    return ""


class TEDSource(JobSource):
    name = "ted"

    def search(self, keywords: str, location: str = "", limit: int = 25,
               remote: bool = False, days: int | None = None) -> list[Job]:
        kw = [w for w in re.split(r"\s+", (keywords or "").lower()) if w]
        cutoff = (date.today() - timedelta(days=days or 60)).strftime("%Y%m%d")
        query = (f"(classification-cpv=72000000 OR classification-cpv=79000000) "
                 f"AND place-of-performance=DNK AND publication-date>={cutoff}")
        # over-fetch when filtering client-side by keyword, so the filter has headroom
        page_size = 50 if kw else max(1, min(limit, 50))
        body = {"query": query, "fields": _FIELDS, "limit": page_size, "page": 1}
        try:
            resp = requests.post(_API, json=body, headers=_HEADERS, timeout=25)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            raise RuntimeError(f"EU TED request failed ({type(e).__name__}).") from e

        jobs: list[Job] = []
        for n in (data.get("notices") if isinstance(data, dict) else None) or []:
            if not isinstance(n, dict):
                continue
            try:
                title = (_lang(n.get("title-proc")) or _lang(n.get("notice-title"))).strip()
                buyer = _lang(n.get("buyer-name")).strip()
                pubnum = str(n.get("publication-number") or "").strip()
                deadline = iso_date(n.get("deadline-receipt-request"))
                desc = strip_html(f"Public-sector consultancy tender (CPV 72/79){f' from {buyer}' if buyer else ''}."
                                  f"{f' Application deadline: {deadline}.' if deadline else ''}")
                if kw and not any(w in f"{title} {buyer} {desc}".lower() for w in kw):
                    continue
                jobs.append(Job(
                    title=title or "Tender",
                    company=buyer or "Danish public sector",
                    location="Denmark",
                    url=f"https://ted.europa.eu/en/notice/{pubnum}/html" if pubnum else "",
                    description=desc,
                    source="EU TED (tender)",
                    source_uid=pubnum,                       # publication-number is the unique notice id

                    posted=iso_date(n.get("publication-date")),
                    employment_type="contract",
                ))
            except Exception:
                continue
            if len(jobs) >= limit:
                break
        return jobs
