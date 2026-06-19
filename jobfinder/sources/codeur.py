"""Codeur.com — French freelance **project** marketplace. Publishes a public, no-key RSS of
every newly-posted client project at ``/projects.rss`` (web dev, design, SEO, marketing,
app/integration work). Every item is a discrete gig → contract/freelance.

Clients post anonymously (no company field) and projects are remote-deliverable; the budget
range + categories sit in the description. French-language, but a Denmark-based freelancer can
take remote work. Personal, low-volume use only.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET

import requests

from .base import Job, JobSource
from .normalize import strip_html, rfc822_date

_RSS = "https://www.codeur.com/projects.rss"
_HEADERS = {"User-Agent": "JobFinder/1.0 (personal job search)"}


class CodeurSource(JobSource):
    name = "codeur"

    def search(self, keywords: str, location: str = "", limit: int = 25,
               remote: bool = False, days: int | None = None) -> list[Job]:
        kw = [w for w in re.split(r"\s+", (keywords or "").lower()) if w]
        try:
            resp = requests.get(_RSS, headers=_HEADERS, timeout=20)
            resp.raise_for_status()
            root = ET.fromstring(resp.content)
        except Exception as e:
            raise RuntimeError(f"Codeur request failed ({type(e).__name__}).") from e

        jobs: list[Job] = []
        for item in root.iter("item"):
            title = (item.findtext("title") or "").strip()
            desc = strip_html(item.findtext("description") or "")
            if kw and not any(w in f"{title} {desc}".lower() for w in kw):
                continue
            jobs.append(Job(
                title=title,
                company="",                                # clients post anonymously
                location="Remote",
                url=(item.findtext("link") or "").strip(),
                description=desc,
                source="Codeur (FR gigs)",
                posted=rfc822_date(item.findtext("pubDate") or ""),
                remote=True,
                employment_type="freelance",               # every listing is a client project
            ))
            if len(jobs) >= limit:
                break
        return jobs
