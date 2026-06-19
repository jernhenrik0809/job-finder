"""Landing.jobs — a large European tech job board (Lisbon-based, EU-wide). Public, no-key
JSON API at ``/api/v1/jobs`` with structured salary (currency + gross range), a per-listing
``remote`` flag, relocation support and country-coded locations — solid EU/remote coverage for
a Denmark-based developer.

The feed carries no company field (the employer lives in the listing URL
``/at/<company>/<slug>``) and the description arrives as several HTML blocks, so company is
recovered from the URL and the HTML is flattened with the shared ``strip_html`` helper. The
public feed takes no query params, so keywords/location are filtered client-side.
"""
from __future__ import annotations

import re
from urllib.parse import urlparse

import requests

from .base import Job, JobSource
from .normalize import strip_html, iso_date

_API = "https://landing.jobs/api/v1/jobs"
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


def _num(v) -> int | None:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def _salary(j: dict) -> str:
    cur = str(j.get("currency_code") or "").strip()
    lo, hi = _num(j.get("gross_salary_low")), _num(j.get("gross_salary_high"))
    if lo and hi:
        return f"{cur} {lo:,}–{hi:,}".strip()
    if lo:
        return f"{cur} {lo:,}+".strip()
    return ""


def _company_from_url(url: str) -> str:
    # listing URLs look like https://landing.jobs/at/<company-slug>/<job-slug>
    try:
        parts = [p for p in urlparse(url).path.split("/") if p]
        if len(parts) >= 2 and parts[0] == "at":
            return parts[1].replace("-", " ").strip().title()
    except Exception:
        pass
    return ""


def _location(j: dict) -> str:
    out = []
    for loc in (j.get("locations") or []):
        if not isinstance(loc, dict):
            continue
        city = str(loc.get("city") or "").strip()
        cc = str(loc.get("country_code") or "").strip().upper()
        bit = ", ".join(p for p in (city, cc) if p)
        if bit:
            out.append(bit)
    return "; ".join(out)


class LandingJobsSource(JobSource):
    name = "landingjobs"

    def search(self, keywords: str, location: str = "", limit: int = 25,
               remote: bool = False, days: int | None = None) -> list[Job]:
        kw = [w for w in re.split(r"\s+", (keywords or "").lower()) if w]
        loc = (location or "").lower().strip()
        try:
            resp = requests.get(_API, headers=_HEADERS, timeout=20)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            raise RuntimeError(f"Landing.jobs request failed ({type(e).__name__}).") from e

        rows = data if isinstance(data, list) else (
            data.get("jobs") if isinstance(data, dict) else None)
        jobs: list[Job] = []
        for j in rows or []:
            if not isinstance(j, dict):                # one malformed entry must not drop the batch
                continue
            try:
                title = str(j.get("title") or "").strip()
                url = str(j.get("url") or "").strip()
                tags = [t for t in (j.get("tags") or []) if isinstance(t, str)]
                bits = [strip_html(j.get(k)) for k in
                        ("role_description", "main_requirements", "nice_to_have", "perks")]
                if tags:
                    bits.append("Skills: " + ", ".join(tags) + ".")
                if j.get("relocation_paid"):
                    bits.append("Relocation paid.")
                desc = strip_html(" ".join(b for b in bits if b))
                loc_str = _location(j) or ("Remote" if j.get("remote") else "")
                hay = f"{title} {desc} {' '.join(tags)}".lower()
                if kw and not any(w in hay for w in kw):
                    continue
                if loc and loc_str and loc not in loc_str.lower():
                    continue                           # unknown (empty) location ≠ a non-match
                jobs.append(Job(
                    title=title,
                    company=_company_from_url(url),
                    location=loc_str,
                    url=url,
                    description=desc,
                    source="Landing.jobs",
                    posted=iso_date(j.get("published_at")),
                    salary=_salary(j),
                    remote=bool(j.get("remote")),
                    employment_type=_emp_type(j.get("type")),
                ))
            except Exception:
                continue
            if len(jobs) >= limit:
                break
        return jobs
