"""Jobindex.dk — Denmark's largest job board (also covers Ofir, now merged into it).

Jobindex has no public JSON API, but it offers an officially-promoted, no-login **RSS**
feed for a search query. This is the sanctioned programmatic surface; we use it politely
for personal, low-volume matching only (no redistribution of the ad text).

The feed is ISO-8859-1, returns the ~20 newest matching ads (no pagination), and each
item's title is "Job title, Company". Parsed with the stdlib + BeautifulSoup (already a
dependency) — no extra package needed.
"""
from __future__ import annotations

import html
import re
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

import requests

from .base import Job, JobSource

_RSS = "https://www.jobindex.dk/jobsoegning.rss"     # note: a DOT, not /jobsoegning/rss
_HEADERS = {"User-Agent": "JobFinder/1.0 (personal job search)"}


from .normalize import strip_html as _strip_html   # shared (was a local copy)


def _posted(pubdate: str) -> str:
    try:
        return parsedate_to_datetime(pubdate).date().isoformat()
    except (TypeError, ValueError):
        return ""


class JobindexSource(JobSource):
    name = "jobindex"

    def search(self, keywords: str, location: str = "", limit: int = 25,
               remote: bool = False, days: int | None = None) -> list[Job]:
        from bs4 import BeautifulSoup

        params = {"q": keywords or ""}
        if days:
            params["jobage"] = days
        try:
            resp = requests.get(_RSS, params=params, headers=_HEADERS, timeout=20)
            resp.raise_for_status()
            root = ET.fromstring(resp.content)       # bytes → honours the ISO-8859-1 XML prolog
        except Exception as e:
            raise RuntimeError(f"Jobindex request failed ({type(e).__name__}).") from e

        loc = location.lower().strip()
        jobs: list[Job] = []
        for item in root.iter("item"):
            raw_title = (item.findtext("title") or "").strip()
            # title is "Job title, Company" — split on the LAST comma
            if ", " in raw_title:
                title, company = raw_title.rsplit(", ", 1)
            else:
                title, company = raw_title, ""

            soup = BeautifulSoup(html.unescape(item.findtext("description") or ""), "html.parser")
            area_el = soup.select_one(".jix_robotjob--area")
            area = area_el.get_text(strip=True) if area_el else ""
            if loc and loc not in area.lower():
                continue

            jobs.append(Job(
                title=title.strip(),
                company=company.strip(),
                location=area,
                url=(item.findtext("link") or "").strip(),
                description=_strip_html(soup.get_text(" ", strip=True)),
                source="Jobindex",
                posted=_posted(item.findtext("pubDate") or ""),
            ))
            if len(jobs) >= limit:
                break
        return jobs
