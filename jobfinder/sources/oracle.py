"""Oracle Recruiting Cloud (ORC) "Candidate Experience" boards — the public, no-key REST
endpoint behind many large employers' careers sites. Used here for major **Danish
universities** (DTU, SDU) that run on Oracle ORC: a high-value academic/public-sector
source with full descriptions and no login.

Generic over a list of (host, site, label) boards; each ORC tenant lives on its own Oracle
pod host with a ``siteNumber`` (e.g. CX_1). One bad board/record never aborts the rest.
"""
from __future__ import annotations

import re

import requests

from .base import Job, JobSource
from .normalize import strip_html, iso_date

_HEADERS = {"User-Agent": "JobFinder/1.0 (personal job search)", "Accept": "application/json"}
_PATH = ("/hcmRestApi/resources/latest/recruitingCEJobRequisitions"
         "?onlyData=true&expand=requisitionList&finder=findReqs;siteNumber={site},limit={limit}")

# Live-verified Danish universities on Oracle ORC (host, siteNumber, label).
_DEFAULT_BOARDS = (
    ("efzu.fa.em2.oraclecloud.com", "CX_1", "DTU"),
    ("fa-eosd-saasfaprod1.fa.ocs.oraclecloud.com", "CX_1001", "SDU (Syddansk Universitet)"),
)


class OracleORCSource(JobSource):
    name = "oracle"

    def __init__(self, boards: tuple = _DEFAULT_BOARDS):
        self.boards = boards

    def search(self, keywords: str, location: str = "", limit: int = 25,
               remote: bool = False, days: int | None = None) -> list[Job]:
        if not self.boards:                  # nothing configured → empty, not a misleading error
            return []
        kw = [w for w in re.split(r"\s+", (keywords or "").lower()) if w]
        loc = (location or "").lower().strip()
        out: list[Job] = []
        errors = 0
        for host, site, label in self.boards:
            if len(out) >= limit:
                break
            url = f"https://{host}{_PATH.format(site=site, limit=max(1, min(limit, 100)))}"
            try:
                resp = requests.get(url, headers=_HEADERS, timeout=25)
                resp.raise_for_status()
                items = resp.json().get("items") or []
                reqs = (items[0].get("requisitionList") if items and isinstance(items[0], dict) else None) or []
            except Exception:
                errors += 1
                continue
            for j in reqs:
                if not isinstance(j, dict):
                    continue
                try:
                    title = (j.get("Title") or "").strip()
                    desc = strip_html(" ".join(s for s in (
                        j.get("ShortDescriptionStr"), j.get("ExternalResponsibilitiesStr"),
                        j.get("ExternalQualificationsStr")) if s))
                    location_str = (j.get("PrimaryLocation") or "").strip()
                    jid = str(j.get("Id") or "").strip()
                    if kw and not any(w in f"{title} {desc}".lower() for w in kw):
                        continue
                    if loc and loc not in location_str.lower():
                        continue
                    out.append(Job(
                        title=title,
                        company=label,
                        location=location_str,
                        url=f"https://{host}/hcmUI/CandidateExperience/en/sites/{site}/job/{jid}" if jid else "",
                        description=desc,
                        source=f"{label} (Oracle ORC)",
                        posted=iso_date(j.get("PostedDate")),
                        remote="REMOTE" in str(j.get("WorkplaceTypeCode") or "").upper(),
                    ))
                except Exception:
                    continue
                if len(out) >= limit:
                    break
        if errors == len(self.boards) and not out:
            raise RuntimeError("Oracle ORC request failed (all boards unavailable).")
        return out
