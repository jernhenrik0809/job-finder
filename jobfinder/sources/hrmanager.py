"""HR-Manager / Talentech JobPortal — the recruitment backbone for Danish public-sector,
university and regional employers. Free, public, no-auth JSON feed per "customer".

The single highest-value Danish public-sector source: the ``statensrekrutteringsloesning_tr``
customer (Statens Rekrutteringsløsning) aggregates vacancies across ~140 Danish state
institutions (ministries, agencies, courts, police, universities migrating in) — a
ToS-clean, programmatic stand-in for the login-gated Jobnet/STAR. We query a curated list
of customer aliases and merge the results.
"""
from __future__ import annotations

import html
import re
from datetime import datetime, timezone

import requests

from .base import Job, JobSource

_API = "https://api.hr-manager.net/JobPortal.svc/{alias}/PositionList/json"
_HEADERS = {"User-Agent": "JobFinder/1.0 (personal job search)"}

# Curated, verified customer aliases. SRL gives broad Danish *state* coverage from one call;
# regionsyddanmark adds regional health/hospital jobs. More can be added over time.
_ALIASES = ("statensrekrutteringsloesning_tr", "regionsyddanmark")


from .normalize import strip_html as _strip_html   # shared (was a local copy)


def _msdate(value) -> str:
    """Parse a .NET '/Date(1780396745000+0200)/' timestamp to a YYYY-MM-DD string."""
    m = re.search(r"/Date\((\d+)", str(value or ""))
    if not m:
        return ""
    try:
        return datetime.fromtimestamp(int(m.group(1)) / 1000, tz=timezone.utc).date().isoformat()
    except (ValueError, OverflowError, OSError):
        return ""


class HRManagerSource(JobSource):
    name = "hrmanager"

    def __init__(self, aliases: tuple[str, ...] = _ALIASES):
        self.aliases = aliases

    def search(self, keywords: str, location: str = "", limit: int = 25,
               remote: bool = False, days: int | None = None) -> list[Job]:
        kw = [w for w in re.split(r"\s+", (keywords or "").lower()) if w]
        loc = (location or "").lower().strip()
        jobs: list[Job] = []
        errors = 0
        for alias in self.aliases:
            if len(jobs) >= limit:
                break
            try:
                resp = requests.get(_API.format(alias=alias),
                                    params={"protype": "RecruitmentProject", "incads": "true"},
                                    headers=_HEADERS, timeout=25)
                resp.raise_for_status()
                items = resp.json().get("Items") or []
            except Exception:
                errors += 1
                continue

            for it in items:
                if not isinstance(it, dict):            # one bad record must not drop the batch
                    continue
                title = (it.get("Name") or "").strip()
                dept = it.get("Department")
                dept = dept if isinstance(dept, dict) else {}
                company = (dept.get("Name") or it.get("CustomerName") or "").strip()
                pos_loc = it.get("PositionLocation")
                pos_loc = pos_loc if isinstance(pos_loc, dict) else {}
                location_str = (it.get("WorkPlace") or dept.get("City")
                                or pos_loc.get("Name") or "").strip()
                ads = it.get("Advertisements")
                first_ad = ads[0] if isinstance(ads, list) and ads else None
                ad_content = first_ad.get("Content") if isinstance(first_ad, dict) else None
                desc = _strip_html(ad_content) or _strip_html(it.get("ShortDescription"))
                if kw and not any(w in f"{title} {desc}".lower() for w in kw):
                    continue
                if loc and loc not in location_str.lower():
                    continue
                jobs.append(Job(
                    title=title,
                    company=company,
                    location=location_str,
                    url=(it.get("AdvertisementUrlSecure") or it.get("AdvertisementUrl") or "").strip(),
                    description=desc,
                    source="HR-Manager (DK public sector)",
                    posted=_msdate(it.get("Published") or it.get("Created")),
                ))
                if len(jobs) >= limit:
                    break

        # only error out if every alias failed and nothing was collected
        if errors == len(self.aliases) and not jobs:
            raise RuntimeError("HR-Manager request failed (all feeds unavailable).")
        return jobs
