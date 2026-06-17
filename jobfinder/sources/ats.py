"""ATS boards — the public, no-key job-board APIs that power companies' own careers pages:
Greenhouse, Lever and Ashby. These give **full job descriptions** straight from the
employer (the most ethical full-text source class — it's the same data on the public
careers site), so they're a high-signal complement to the aggregators.

Each ATS is queried per *company board token*. We ship a small curated, Denmark/Nordic-
relevant default list and let the user override it with ``JOBFINDER_ATS_COMPANIES`` (a
comma-separated list of ``provider:token`` entries, e.g. ``greenhouse:trustpilot,ashby:Pleo``).
One bad/empty board never aborts the others.
"""
from __future__ import annotations

import html
import os
import re

import requests

from .base import Job, JobSource
from .normalize import strip_html, iso_date, epoch_date

_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
    "Accept": "application/json",
}

# Curated, live-verified Denmark/Nordic boards (provider, company-token). Override via
# JOBFINDER_ATS_COMPANIES. Tokens must match the company's exact board slug.
_DEFAULT_BOARDS = (
    ("greenhouse", "trustpilot"),     # Danish-founded, Copenhagen HQ
    ("greenhouse", "toogoodtogo"),    # Copenhagen-founded
    ("lever", "veo"),                 # Copenhagen (Veo Technologies)
    ("ashby", "Corti"),               # Copenhagen AI healthcare
    ("ashby", "Pleo"),                # Danish fintech
    ("ashby", "Lunar"),               # Nordic neobank
)


def _boards() -> list[tuple[str, str]]:
    raw = os.environ.get("JOBFINDER_ATS_COMPANIES", "").strip()
    if not raw:
        return list(_DEFAULT_BOARDS)
    out = []
    for part in raw.split(","):
        part = part.strip()
        if ":" in part:
            provider, token = part.split(":", 1)
            provider, token = provider.strip().lower(), token.strip()
            if provider in ("greenhouse", "lever", "ashby") and token:
                out.append((provider, token))
    return out


def _pretty(token: str) -> str:
    return token.replace("-", " ").replace("_", " ").strip().title()


def _greenhouse(company: str) -> list[Job]:
    url = f"https://boards-api.greenhouse.io/v1/boards/{company}/jobs?content=true"
    resp = requests.get(url, headers=_HEADERS, timeout=20)
    resp.raise_for_status()
    jobs = []
    for j in (resp.json().get("jobs") or []):
        if not isinstance(j, dict):
            continue
        loc = j.get("location") if isinstance(j.get("location"), dict) else {}
        jobs.append(Job(
            title=(j.get("title") or "").strip(),
            company=(j.get("company_name") or _pretty(company)).strip(),
            location=(loc.get("name") or "").strip(),
            url=(j.get("absolute_url") or "").strip(),
            # content is HTML-entity-encoded HTML → unescape first, then strip tags
            description=strip_html(html.unescape(j.get("content") or "")),
            source="ATS (Greenhouse)",
            posted=iso_date(j.get("updated_at") or j.get("first_published")),
        ))
    return jobs


def _lever(company: str) -> list[Job]:
    url = f"https://api.lever.co/v0/postings/{company}?mode=json"
    resp = requests.get(url, headers=_HEADERS, timeout=20)
    resp.raise_for_status()
    data = resp.json()
    jobs = []
    for j in (data if isinstance(data, list) else []):
        if not isinstance(j, dict):
            continue
        cats = j.get("categories") if isinstance(j.get("categories"), dict) else {}
        workplace = str(j.get("workplaceType") or "").lower()
        jobs.append(Job(
            title=(j.get("text") or "").strip(),
            company=_pretty(company),
            location=(cats.get("location") or "").strip(),
            url=(j.get("hostedUrl") or "").strip(),
            description=strip_html(j.get("descriptionPlain") or j.get("description")),
            source="ATS (Lever)",
            posted=epoch_date(j.get("createdAt")),
            remote=workplace in ("remote", "hybrid"),
        ))
    return jobs


def _ashby(company: str) -> list[Job]:
    url = f"https://api.ashbyhq.com/posting-api/job-board/{company}?includeCompensation=true"
    resp = requests.get(url, headers=_HEADERS, timeout=20)
    resp.raise_for_status()
    jobs = []
    for j in (resp.json().get("jobs") or []):
        if not isinstance(j, dict) or j.get("isListed") is False:
            continue
        jobs.append(Job(
            title=(j.get("title") or "").strip(),
            company=_pretty(company),
            location=(j.get("location") or "").strip(),
            url=(j.get("jobUrl") or j.get("applyUrl") or "").strip(),
            description=strip_html(j.get("descriptionPlain") or j.get("descriptionHtml")),
            source="ATS (Ashby)",
            posted=iso_date(j.get("publishedAt")),
            remote=bool(j.get("isRemote")) or str(j.get("workplaceType") or "").lower() == "remote",
        ))
    return jobs


_FETCH = {"greenhouse": _greenhouse, "lever": _lever, "ashby": _ashby}


class ATSSource(JobSource):
    name = "ats"

    def __init__(self, boards: list[tuple[str, str]] | None = None):
        self.boards = boards if boards is not None else _boards()

    def search(self, keywords: str, location: str = "", limit: int = 25,
               remote: bool = False, days: int | None = None) -> list[Job]:
        if not self.boards:                  # nothing configured (or env fully malformed) → empty,
            return []                         # not a misleading "all boards unavailable" error
        kw = [w for w in re.split(r"\s+", (keywords or "").lower()) if w]
        loc = (location or "").lower().strip()
        out: list[Job] = []
        errors = 0
        for provider, company in self.boards:
            if len(out) >= limit:
                break
            fetch = _FETCH.get(provider)
            if fetch is None:
                continue
            try:
                jobs = fetch(company)
            except Exception:
                errors += 1
                continue
            for job in jobs:
                if kw and not any(w in f"{job.title} {job.description}".lower() for w in kw):
                    continue
                if loc and loc not in job.location.lower():
                    continue
                out.append(job)
                if len(out) >= limit:
                    break
        if errors == len(self.boards) and not out:
            raise RuntimeError("ATS request failed (all boards unavailable).")
        return out
