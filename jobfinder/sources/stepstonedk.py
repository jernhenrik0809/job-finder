"""StepStone.dk — major Danish general/professional job board (StepStone Group, runs on
the Jobindex platform). Free no-login RSS, the same family as Jobindex / it-jobbank.

The Denmark-scoped feed lives at ``/job/danmark`` and the keyword param is ``q=`` (``what=``
is silently ignored). Locations/company sit inside the HTML ``<description>`` fragment
(``span.job-location`` / ``div.job-company``), not the ``.jix_robotjob--area`` span Jobindex
uses. ISO-8859-1, parsed with the stdlib + BeautifulSoup. Personal, low-volume use only.
"""
from __future__ import annotations

import html
import re
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

import requests

from .base import Job, JobSource

_RSS = "https://www.stepstone.dk/job/danmark"
_HEADERS = {"User-Agent": "JobFinder/1.0 (personal job search)"}


def _strip_html(text) -> str:
    text = re.sub(r"<[^>]+>", " ", str(text or ""))
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def _posted(pubdate: str) -> str:
    try:
        return parsedate_to_datetime(pubdate).date().isoformat()
    except (TypeError, ValueError):
        return ""


class StepStoneDkSource(JobSource):
    name = "stepstonedk"

    def search(self, keywords: str, location: str = "", limit: int = 25,
               remote: bool = False, days: int | None = None) -> list[Job]:
        from bs4 import BeautifulSoup

        try:
            resp = requests.get(_RSS, params={"q": keywords or "", "format": "rss"},
                                headers=_HEADERS, timeout=20)
            resp.raise_for_status()
            root = ET.fromstring(resp.content)       # bytes → honours the ISO-8859-1 prolog
        except Exception as e:
            raise RuntimeError(f"StepStone.dk request failed ({type(e).__name__}).") from e

        loc = location.lower().strip()
        jobs: list[Job] = []
        for item in root.iter("item"):
            raw_title = (item.findtext("title") or "").strip()
            if ", " in raw_title:
                title, company = raw_title.rsplit(", ", 1)
            else:
                title, company = raw_title, ""

            soup = BeautifulSoup(html.unescape(item.findtext("description") or ""), "html.parser")
            comp_el = soup.select_one(".job-company")
            if comp_el and comp_el.get_text(strip=True):
                company = comp_el.get_text(strip=True)
            loc_el = soup.select_one(".job-location")
            area = loc_el.get_text(strip=True) if loc_el else ""
            body_el = soup.select_one(".job-body")
            desc = _strip_html(body_el.get_text(" ", strip=True)) if body_el else ""

            if loc and loc not in area.lower():
                continue

            jobs.append(Job(
                title=title.strip(),
                company=company.strip(),
                location=area,
                url=(item.findtext("link") or "").strip(),
                description=desc,
                source="StepStone.dk",
                posted=_posted(item.findtext("pubDate") or ""),
            ))
            if len(jobs) >= limit:
                break
        return jobs
