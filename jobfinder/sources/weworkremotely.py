"""We Work Remotely — free, no-login remote-jobs RSS (no key). Global remote roles.

No keyword/location query params, so we fetch the feed and filter client-side. Each item's
``<title>`` is "Company: Role" (split on the first colon) and the location lives in
``<region>`` (usually "Anywhere in the World"). Personal, low-volume use only.
"""
from __future__ import annotations

import html
import re
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

import requests

from .base import Job, JobSource

_RSS = "https://weworkremotely.com/remote-jobs.rss"
_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
}


from .normalize import strip_html as _strip_html   # shared (was a local copy)


def _posted(pubdate: str) -> str:
    try:
        return parsedate_to_datetime(pubdate).date().isoformat()
    except (TypeError, ValueError):
        return ""


class WeWorkRemotelySource(JobSource):
    name = "weworkremotely"

    def search(self, keywords: str, location: str = "", limit: int = 25,
               remote: bool = False, days: int | None = None) -> list[Job]:
        kw = [w for w in re.split(r"\s+", (keywords or "").lower()) if w]
        loc = (location or "").lower().strip()
        try:
            resp = requests.get(_RSS, headers=_HEADERS, timeout=20)
            resp.raise_for_status()
            root = ET.fromstring(resp.content)
        except Exception as e:
            raise RuntimeError(f"We Work Remotely request failed ({type(e).__name__}).") from e

        jobs: list[Job] = []
        for item in root.iter("item"):
            raw_title = (item.findtext("title") or "").strip()
            if ":" in raw_title:
                company, title = raw_title.split(":", 1)
            else:
                company, title = "", raw_title
            region = (item.findtext("region") or "").strip()
            desc = _strip_html(item.findtext("description") or "")

            if kw and not any(w in f"{title} {company} {desc}".lower() for w in kw):
                continue
            if loc and loc not in region.lower():
                continue

            jobs.append(Job(
                title=title.strip(),
                company=company.strip(),
                location=region or "Remote",
                url=(item.findtext("link") or "").strip(),
                description=desc,
                source="We Work Remotely",
                posted=_posted(item.findtext("pubDate") or ""),
                remote=True,
            ))
            if len(jobs) >= limit:
                break
        return jobs
