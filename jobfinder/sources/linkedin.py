"""LinkedIn job source via the public "jobs-guest" search endpoint (no login).

LinkedIn exposes an unauthenticated guest endpoint that powers the public job
search results you see when not logged in:

    https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search

It returns an HTML fragment of job *cards* (title, company, location, link,
posted-date) but NOT the full description. The description lives on a per-job
guest endpoint:

    https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/<jobId>

Because the matcher benefits hugely from the description, we fetch those too,
with a small thread pool, jittered delays and graceful back-off so we stay
polite and survive rate-limiting (HTTP 429).

This is intended for **personal, low-volume** job searching. It is not an
official API; treat it gently. If LinkedIn blocks the request, the app falls
back to the free API sources (Remotive / Arbeitnow).
"""
from __future__ import annotations

import html
import random
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

from .base import Job, JobSource

_SEARCH_URL = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
_JOB_URL = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# f_TPR (time posted) values
_TPR = {1: "r86400", 7: "r604800", 14: "r1209600", 30: "r2592000"}
# f_WT (workplace type): 2 == remote
_REMOTE_WT = "2"

# A small geoId lookup improves LinkedIn location filtering (it expects numeric
# geoIds, not place names). Matched on a case-insensitive substring of `location`.
_GEO_IDS = {
    "worldwide": "92000000",
    "united states": "103644278",
    "usa": "103644278",
    "united kingdom": "101165590",
    "uk": "101165590",
    "england": "102299470",
    "london": "102257491",
    "canada": "101174742",
    "germany": "101282230",
    "france": "105015875",
    "netherlands": "102890719",
    "ireland": "104738515",
    "india": "102713980",
    "australia": "101452733",
    "spain": "105646813",
    "italy": "103350119",
    "denmark": "104514075",
    "sweden": "105117694",
    "norway": "103819153",
    "switzerland": "106693272",
    "poland": "105072130",
    "singapore": "102454443",
    "remote": "92000000",
    "europe": "100506914",
}


def _resolve_geo_id(location: str) -> str | None:
    if not location:
        return None
    loc = location.lower().strip()
    if loc in _GEO_IDS:
        return _GEO_IDS[loc]
    for name, gid in _GEO_IDS.items():
        if name in loc:
            return gid
    return None


from .normalize import strip_html as _strip_html   # shared (was a local copy)


def _tpr_param(days: int | None) -> str | None:
    if not days:
        return None
    for threshold in (1, 7, 14, 30):
        if days <= threshold:
            return _TPR[threshold]
    return _TPR[30]


class LinkedInSource(JobSource):
    name = "linkedin"

    def __init__(self, fetch_descriptions: bool = True, max_workers: int = 3,
                 min_delay: float = 0.8, max_delay: float = 2.0,
                 page_min_delay: float = 2.0, page_max_delay: float = 4.5):
        # Description fetches use the shorter (min/max) delay; search-page fetches
        # use the longer (page_*) delay since paginating is what triggers LinkedIn's
        # rate-limiter around page ~10.
        self.fetch_descriptions = fetch_descriptions
        self.max_workers = max_workers
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.page_min_delay = page_min_delay
        self.page_max_delay = page_max_delay
        self.session = requests.Session()
        self.session.headers.update(_HEADERS)
        self.last_warning: str | None = None

    # -- public ------------------------------------------------------------
    def search(self, keywords: str, location: str = "", limit: int = 25,
               remote: bool = False, days: int | None = None) -> list[Job]:
        self.last_warning = None
        cards = self._search_cards(keywords, location, limit, remote, days)
        if not cards:
            return []
        if self.fetch_descriptions:
            self._enrich_descriptions(cards)
        return cards

    # -- internals ---------------------------------------------------------
    def _search_cards(self, keywords, location, limit, remote, days) -> list[Job]:
        jobs: list[Job] = []
        seen: set[str] = set()
        start = 0
        tpr = _tpr_param(days)
        empty_pages = 0

        while len(jobs) < limit and start < 1000:
            params = {"keywords": keywords, "location": location, "start": start}
            geo_id = _resolve_geo_id(location)
            if geo_id:
                params["geoId"] = geo_id
            if tpr:
                params["f_TPR"] = tpr
            if remote:
                params["f_WT"] = _REMOTE_WT

            try:
                resp = self.session.get(_SEARCH_URL, params=params, timeout=20)
            except requests.RequestException as e:
                self.last_warning = f"LinkedIn request error: {e}"
                break

            if resp.status_code == 429:
                self.last_warning = "LinkedIn rate-limited the search (HTTP 429). Returning partial results."
                break
            if resp.status_code != 200 or not resp.text.strip():
                if start == 0:
                    self.last_warning = f"LinkedIn returned HTTP {resp.status_code}."
                break

            page_jobs = self._parse_cards(resp.text)
            if not page_jobs:
                empty_pages += 1
                if empty_pages >= 2:
                    break
            else:
                empty_pages = 0

            for job in page_jobs:
                if job.id not in seen:
                    seen.add(job.id)
                    jobs.append(job)
                    if len(jobs) >= limit:
                        break

            # LinkedIn's guest endpoint paginates in steps of 25.
            start += 25
            time.sleep(random.uniform(self.page_min_delay, self.page_max_delay))

        return jobs[:limit]

    def _parse_cards(self, markup: str) -> list[Job]:
        try:
            from bs4 import BeautifulSoup
        except ImportError as e:
            raise RuntimeError("LinkedIn source needs beautifulsoup4 (pip install beautifulsoup4).") from e

        soup = BeautifulSoup(markup, "html.parser")
        jobs: list[Job] = []
        for card in soup.select("li"):
            base = card.find(class_="base-card") or card
            title_el = base.select_one(".base-search-card__title")
            company_el = base.select_one(".base-search-card__subtitle")
            location_el = base.select_one(".job-search-card__location")
            link_el = base.select_one("a.base-card__full-link") or base.find("a", href=True)
            date_el = base.select_one("time")

            if not title_el:
                continue

            url = link_el["href"].split("?")[0] if link_el and link_el.has_attr("href") else ""
            job_id = self._extract_job_id(base, url)

            jobs.append(Job(
                title=title_el.get_text(strip=True),
                company=company_el.get_text(strip=True) if company_el else "",
                location=location_el.get_text(strip=True) if location_el else "",
                url=url,
                description="",
                source="LinkedIn",
                posted=(date_el.get("datetime", "") if date_el else ""),
                job_skills=[],
            ))
            # stash the id on the object via a private attr for enrichment
            jobs[-1]._li_id = job_id  # type: ignore[attr-defined]
        return jobs

    @staticmethod
    def _extract_job_id(base, url: str) -> str | None:
        # 1) from data-entity-urn="urn:li:jobPosting:1234567890"
        holder = base.find(attrs={"data-entity-urn": True})
        if holder:
            m = re.search(r"jobPosting:(\d+)", holder["data-entity-urn"])
            if m:
                return m.group(1)
        # 2) from the job URL .../view/title-1234567890
        m = re.search(r"-(\d{6,})(?:\?|$)", url)
        if m:
            return m.group(1)
        m = re.search(r"/(\d{6,})(?:\?|$)", url)
        return m.group(1) if m else None

    def _enrich_descriptions(self, jobs: list[Job]) -> None:
        targets = [j for j in jobs if getattr(j, "_li_id", None)]
        if not targets:
            return

        def fetch(job: Job) -> None:
            job_id = getattr(job, "_li_id")
            try:
                time.sleep(random.uniform(self.min_delay, self.max_delay))
                resp = self.session.get(_JOB_URL.format(job_id=job_id), timeout=20)
                if resp.status_code == 200:
                    job.description = self._parse_description(resp.text)
                elif resp.status_code == 429:
                    self.last_warning = "LinkedIn rate-limited description fetch (HTTP 429); some descriptions may be missing."
            except requests.RequestException:
                pass  # keep the job; matcher falls back to title

        with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
            futures = [pool.submit(fetch, j) for j in targets]
            for _ in as_completed(futures):
                pass

    def _parse_description(self, markup: str) -> str:
        try:
            from bs4 import BeautifulSoup
        except ImportError:
            return _strip_html(markup)
        soup = BeautifulSoup(markup, "html.parser")
        el = (soup.select_one(".description__text")
              or soup.select_one(".show-more-less-html__markup")
              or soup.select_one(".description"))
        return _strip_html(str(el)) if el else ""
