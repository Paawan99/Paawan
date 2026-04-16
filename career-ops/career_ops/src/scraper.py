"""Job-board scrapers using public JSON endpoints.

Greenhouse, Ashby, and Lever all expose unauthenticated JSON feeds for the
job listings on customer career pages. This module wraps those feeds.

Why these three boards:
- they cover ~70% of US/EU tech postings
- no API key required
- JSON output is stable and machine-readable

Anything else (LinkedIn, Indeed, company career pages without a board) requires
HTML scraping and is out of scope for this module.
"""

from __future__ import annotations

import logging
import time
from typing import Iterable, List
from urllib.parse import urlparse

import requests

from .models import Job

log = logging.getLogger(__name__)

USER_AGENT = "career-ops/0.1 (+https://github.com/paawan99/paawan)"
TIMEOUT = 20
RETRY_BACKOFF = (1, 2, 4)


def _get(url: str) -> dict | list | None:
    """GET with bounded retry; returns parsed JSON or None."""
    for attempt, wait in enumerate(RETRY_BACKOFF, start=1):
        try:
            r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
            if r.status_code == 404:
                log.warning("404 %s", url)
                return None
            r.raise_for_status()
            return r.json()
        except (requests.RequestException, ValueError) as e:
            log.warning("attempt %d/%d failed for %s: %s", attempt, len(RETRY_BACKOFF), url, e)
            if attempt < len(RETRY_BACKOFF):
                time.sleep(wait)
    return None


def fetch_greenhouse(slug: str) -> List[Job]:
    """Greenhouse: https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"""
    url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"
    data = _get(url)
    if not data or "jobs" not in data:
        return []
    out: List[Job] = []
    for j in data["jobs"]:
        out.append(
            Job(
                source="greenhouse",
                company=slug,
                job_id=str(j.get("id", "")),
                title=j.get("title", ""),
                location=(j.get("location") or {}).get("name", ""),
                department=", ".join(d.get("name", "") for d in j.get("departments", [])),
                url=j.get("absolute_url", ""),
                description_html=j.get("content", ""),
                posted_at=j.get("updated_at", ""),
            )
        )
    return out


def fetch_ashby(slug: str) -> List[Job]:
    """Ashby: https://api.ashbyhq.com/posting-api/job-board/{slug}"""
    url = f"https://api.ashbyhq.com/posting-api/job-board/{slug}"
    data = _get(url)
    if not data or "jobs" not in data:
        return []
    out: List[Job] = []
    for j in data["jobs"]:
        out.append(
            Job(
                source="ashby",
                company=slug,
                job_id=str(j.get("id", "")),
                title=j.get("title", ""),
                location=j.get("location", ""),
                department=j.get("department", ""),
                url=j.get("jobUrl", ""),
                description_html=j.get("descriptionHtml", "") or j.get("description", ""),
                posted_at=j.get("publishedAt", ""),
            )
        )
    return out


def fetch_lever(slug: str) -> List[Job]:
    """Lever: https://api.lever.co/v0/postings/{slug}?mode=json"""
    url = f"https://api.lever.co/v0/postings/{slug}?mode=json"
    data = _get(url)
    if not isinstance(data, list):
        return []
    out: List[Job] = []
    for j in data:
        cats = j.get("categories", {}) or {}
        out.append(
            Job(
                source="lever",
                company=slug,
                job_id=str(j.get("id", "")),
                title=j.get("text", ""),
                location=cats.get("location", ""),
                department=cats.get("team", "") or cats.get("department", ""),
                url=j.get("hostedUrl", ""),
                description_html=j.get("descriptionPlain", "") or j.get("description", ""),
                posted_at=str(j.get("createdAt", "")),
            )
        )
    return out


_DISPATCH = {
    "greenhouse": fetch_greenhouse,
    "ashby": fetch_ashby,
    "lever": fetch_lever,
}


def scan_companies(companies: Iterable[dict]) -> List[Job]:
    """Iterate config entries: [{board, slug}, ...] and return all jobs."""
    jobs: List[Job] = []
    for entry in companies:
        board = entry.get("board")
        slug = entry.get("slug")
        fn = _DISPATCH.get(board)
        if not fn or not slug:
            log.warning("skipping invalid entry: %s", entry)
            continue
        log.info("fetching %s/%s", board, slug)
        jobs.extend(fn(slug))
    return jobs


def resolve_single_url(url: str) -> Job | None:
    """Try to fetch one specific job URL by inferring board + slug + id."""
    p = urlparse(url)
    host = p.netloc.lower()
    if "greenhouse.io" in host:
        # boards.greenhouse.io/<slug>/jobs/<id>
        parts = [x for x in p.path.split("/") if x]
        if len(parts) >= 3 and parts[-2] == "jobs":
            slug, jid = parts[0], parts[-1]
            for j in fetch_greenhouse(slug):
                if j.job_id == jid:
                    return j
    if "ashbyhq.com" in host or "jobs.ashbyhq.com" in host:
        parts = [x for x in p.path.split("/") if x]
        if parts:
            slug = parts[0]
            jid = parts[-1]
            for j in fetch_ashby(slug):
                if j.job_id == jid or j.url.rstrip("/").endswith(jid):
                    return j
    if "lever.co" in host:
        parts = [x for x in p.path.split("/") if x]
        if len(parts) >= 2:
            slug, jid = parts[0], parts[-1]
            for j in fetch_lever(slug):
                if j.job_id == jid:
                    return j
    return None
