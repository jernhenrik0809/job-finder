"""JSearch (RapidAPI) — aggregates Google for Jobs (LinkedIn/Indeed/Glassdoor).

This is the most "LinkedIn-comparable" reliable fallback. It needs a free RapidAPI
key (~200 requests/month free). Set it via the environment:

    setx RAPIDAPI_KEY "your-key"      # Windows (new terminal afterwards)

or pass it on the SearchSettings. Without a key this source raises a clear error
and the app simply skips it.
"""
from __future__ import annotations

import os

import requests

from .base import Job, JobSource

_API = "https://jsearch.p.rapidapi.com/search"


def _api_key() -> str | None:
    return os.environ.get("RAPIDAPI_KEY") or os.environ.get("JSEARCH_API_KEY")


class JSearchSource(JobSource):
    name = "jsearch"

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or _api_key()

    def search(self, keywords: str, location: str = "", limit: int = 25,
               remote: bool = False, days: int | None = None) -> list[Job]:
        if not self.api_key:
            raise RuntimeError(
                "JSearch needs a RapidAPI key. Set RAPIDAPI_KEY in your environment "
                "(free key at https://rapidapi.com/letscrape-6bRBa3QguO5/api/jsearch)."
            )
        query = keywords
        if location:
            query = f"{keywords} in {location}"
        params = {
            "query": query,
            "page": "1",
            "num_pages": str(max(1, min(3, (limit + 9) // 10))),
        }
        if remote:
            params["work_from_home"] = "true"
        if days:
            params["date_posted"] = "today" if days <= 1 else ("week" if days <= 7 else "month")

        headers = {
            "X-RapidAPI-Key": self.api_key,
            "X-RapidAPI-Host": "jsearch.p.rapidapi.com",
        }
        try:
            resp = requests.get(_API, params=params, headers=headers, timeout=25)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            raise RuntimeError(f"JSearch request failed: {e}") from e

        jobs: list[Job] = []
        for item in data.get("data", [])[:limit]:
            city = item.get("job_city") or ""
            country = item.get("job_country") or ""
            loc = ", ".join(p for p in (city, country) if p) or ("Remote" if item.get("job_is_remote") else "")
            salary = ""
            if item.get("job_min_salary") and item.get("job_max_salary"):
                cur = item.get("job_salary_currency", "")
                salary = f"{cur}{int(item['job_min_salary']):,}–{int(item['job_max_salary']):,}"
            jobs.append(Job(
                title=(item.get("job_title") or "").strip(),
                company=(item.get("employer_name") or "").strip(),
                location=loc,
                url=item.get("job_apply_link") or item.get("job_google_link", ""),
                description=item.get("job_description", "") or "",
                source=f"JSearch/{item.get('job_publisher', 'Google Jobs')}",
                posted=(item.get("job_posted_at_datetime_utc") or "")[:10],
                salary=salary,
                remote=bool(item.get("job_is_remote")),
            ))
        return jobs
