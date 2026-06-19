"""Remote / freelance job boards built on **WP Job Manager**, which exposes a public
no-key RSS feed at ``?feed=job_feed`` with structured ``job_listing:*`` fields
(company / location / job_type). One shared parser covers every such board; each concrete
source just sets its feed URL + label.

Currently: Jobspresso and Authentic Jobs — curated remote boards with a healthy
contract/freelance mix (the ``job_type`` field tags it, so they feed the "consulting/
contract only" filter). Personal, low-volume use only.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET

import requests

from .base import Job, JobSource
from .normalize import strip_html, rfc822_date

_HEADERS = {"User-Agent": "JobFinder/1.0 (personal job search)"}


def _emp_type(job_type: str) -> str:
    jt = (job_type or "").strip().lower()
    if "contract" in jt:
        return "contract"
    if "freelance" in jt:
        return "freelance"
    return ""


class _WPJobFeed(JobSource):
    """Base for a WP Job Manager ``?feed=job_feed`` board. Subclasses set ``_FEED``/``_LABEL``."""
    _FEED = ""
    _LABEL = ""

    def search(self, keywords: str, location: str = "", limit: int = 25,
               remote: bool = False, days: int | None = None) -> list[Job]:
        kw = [w for w in re.split(r"\s+", (keywords or "").lower()) if w]
        loc = (location or "").lower().strip()
        try:
            resp = requests.get(self._FEED, headers=_HEADERS, timeout=20)
            resp.raise_for_status()
            root = ET.fromstring(resp.content)
        except Exception as e:
            raise RuntimeError(f"{self._LABEL} request failed ({type(e).__name__}).") from e

        jobs: list[Job] = []
        for item in root.iter("item"):
            # collect children by local name (strip the job_listing:/content: namespaces).
            # job_type can repeat (WP taxonomy is many-to-many) — accumulate all of them so a
            # "Full Time" + "Freelance" listing isn't mis-classified by feed ordering (last-wins).
            f: dict[str, str] = {}
            job_types: list[str] = []
            for child in item:
                local = child.tag.split("}")[-1]
                if local == "job_type":
                    job_types.append(child.text or "")
                f[local] = child.text or ""
            title = f.get("title", "").strip()
            company = f.get("company", "").strip()
            loc_name = f.get("location", "").strip()
            desc = strip_html(f.get("encoded") or f.get("description"))
            if kw and not any(w in f"{title} {company} {desc}".lower() for w in kw):
                continue
            if loc and loc_name and loc not in loc_name.lower():
                continue                               # unknown (empty) location ≠ a non-match
            jobs.append(Job(
                title=title,
                company=company,
                location=loc_name or "Remote",
                url=f.get("link", "").strip(),
                description=desc,
                source=self._LABEL,
                posted=rfc822_date(f.get("pubDate")),
                remote=True,
                employment_type=_emp_type(" ".join(job_types)),
            ))
            if len(jobs) >= limit:
                break
        return jobs


class JobspressoSource(_WPJobFeed):
    name = "jobspresso"
    _FEED = "https://jobspresso.co/?feed=job_feed"
    _LABEL = "Jobspresso"


class AuthenticJobsSource(_WPJobFeed):
    name = "authenticjobs"
    _FEED = "https://authenticjobs.com/?feed=job_feed"
    _LABEL = "Authentic Jobs"


class EURemoteJobsSource(_WPJobFeed):
    # EU-wide remote board; company/location aren't separate XML fields here (they live in the
    # description body), so company comes up "" and location defaults to "Remote" — acceptable.
    name = "euremotejobs"
    _FEED = "https://euremotejobs.com/?feed=job_feed"
    _LABEL = "EU Remote Jobs"
