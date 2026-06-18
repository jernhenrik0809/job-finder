"""Hacker News monthly "Freelancer? Seeking freelancer?" threads — real freelance/contract
gigs, via the free public Algolia HN Search API (no key).

Two steps: find the latest monthly thread (search_by_date), then fetch its comment tree
(items/{id}). Each top-level comment that begins "SEEKING FREELANCER" is a gig (a project to
do); "SEEKING WORK" comments are freelancers offering themselves and are skipped. Tech- and
remote-skewed, modest volume, high signal.
"""
from __future__ import annotations

import re

import requests

from .base import Job, JobSource
from .normalize import strip_html, iso_date

_SEARCH = "https://hn.algolia.com/api/v1/search_by_date"
_ITEMS = "https://hn.algolia.com/api/v1/items/"
_HEADERS = {"User-Agent": "JobFinder/1.0 (personal job search)"}


def _latest_thread_id() -> str | None:
    resp = requests.get(_SEARCH, params={"query": "Freelancer Seeking freelancer",
                                         "tags": "story", "hitsPerPage": 10},
                        headers=_HEADERS, timeout=20)
    resp.raise_for_status()
    for hit in resp.json().get("hits") or []:
        if "seeking freelancer" in (hit.get("title") or "").lower():
            return hit.get("objectID")
    return None


class HackerNewsSource(JobSource):
    name = "hackernews"

    def search(self, keywords: str, location: str = "", limit: int = 25,
               remote: bool = False, days: int | None = None) -> list[Job]:
        kw = [w for w in re.split(r"\s+", (keywords or "").lower()) if w]
        loc = (location or "").lower().strip()
        try:
            thread_id = _latest_thread_id()
            if not thread_id:
                return []
            resp = requests.get(f"{_ITEMS}{thread_id}", headers=_HEADERS, timeout=20)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            raise RuntimeError(f"Hacker News request failed ({type(e).__name__}).") from e

        jobs: list[Job] = []
        for c in (data.get("children") if isinstance(data, dict) else None) or []:
            if not isinstance(c, dict) or not c.get("text"):
                continue
            raw = str(c["text"])
            # header line = text before the first paragraph break
            header = strip_html(re.split(r"<p>", raw, maxsplit=1)[0])
            if "seeking freelancer" not in header.lower():
                continue                                   # skip "SEEKING WORK" (freelancers) + chatter
            desc = strip_html(raw)
            if kw and not any(w in f"{header} {desc}".lower() for w in kw):
                continue
            if loc and loc not in header.lower() and loc not in desc.lower():
                continue
            jobs.append(Job(
                title=header[:140] or "Freelance gig",
                company="",                                # individual/client-posted, like Freelancer.com
                location="Remote" if "remote" in header.lower() else "",
                url=f"https://news.ycombinator.com/item?id={c['id']}" if c.get("id") else "",
                description=desc,
                source="Hacker News (gigs)",
                posted=iso_date(c.get("created_at")),
                remote="remote" in f"{header} {desc}".lower(),
                employment_type="freelance",
            ))
            if len(jobs) >= limit:
                break
        return jobs
