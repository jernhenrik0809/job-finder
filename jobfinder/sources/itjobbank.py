"""it-jobbank.dk — Denmark's leading IT/tech job board (StepStone family).

No public JSON API, but a free no-login RSS feed (the same StepStone-family RSS shape as
Jobindex). Personal, low-volume use only. Parsed with the stdlib + BeautifulSoup.
"""
from __future__ import annotations

import html
import re
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

import requests

from .base import Job, JobSource

_RSS = "https://www.it-jobbank.dk/jobsoegning"
_HEADERS = {"User-Agent": "JobFinder/1.0 (personal job search)"}


from .normalize import strip_html as _strip_html   # shared (was a local copy)


def _posted(pubdate: str) -> str:
    try:
        return parsedate_to_datetime(pubdate).date().isoformat()
    except (TypeError, ValueError):
        return ""


class ItJobbankSource(JobSource):
    name = "itjobbank"

    def search(self, keywords: str, location: str = "", limit: int = 25,
               remote: bool = False, days: int | None = None) -> list[Job]:
        from bs4 import BeautifulSoup

        try:
            resp = requests.get(_RSS, params={"q": keywords or "", "format": "rss"},
                                headers=_HEADERS, timeout=20)
            resp.raise_for_status()
            root = ET.fromstring(resp.content)       # bytes → honours the feed's XML prolog encoding
        except Exception as e:
            raise RuntimeError(f"it-jobbank request failed ({type(e).__name__}).") from e

        loc = location.lower().strip()
        jobs: list[Job] = []
        for item in root.iter("item"):
            raw_title = (item.findtext("title") or "").strip()
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
                source="it-jobbank",
                posted=_posted(item.findtext("pubDate") or ""),
            ))
            if len(jobs) >= limit:
                break
        return jobs
