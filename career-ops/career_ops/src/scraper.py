"""Job-board scrapers using public JSON endpoints.

Boards covered:
- Greenhouse, Ashby, Lever  -- common for tech/fintech
- Workday CXS               -- used by all Big Six Canadian banks and most
                               large credit unions

All endpoints are public and unauthenticated. Anything else (LinkedIn,
Indeed, custom HR portals) needs HTML scraping or a paid API and is out
of scope for this module.
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
TIMEOUT = 25
RETRY_BACKOFF = (1, 2, 4)

# Common Canadian city/province tokens for client-side location filtering.
# Workday tenants reject a "country" facet in the request body, so we fetch
# everything and filter here.
_CANADA_HINTS = (
    "canada", "canadian",
    # provinces
    "ontario", "quebec", "british columbia", "b.c.", "bc,",
    "alberta", "manitoba", "saskatchewan", "nova scotia", "new brunswick",
    "newfoundland", "prince edward", "p.e.i.", "nwt", "yukon", "nunavut",
    # major cities
    "toronto", "mississauga", "brampton", "markham", "scarborough", "etobicoke",
    "ottawa", "hamilton", "london", "kitchener", "waterloo", "windsor",
    "montreal", "quebec city", "laval", "gatineau", "sherbrooke",
    "vancouver", "burnaby", "richmond", "surrey", "victoria", "kelowna",
    "calgary", "edmonton", "red deer", "lethbridge",
    "winnipeg", "regina", "saskatoon", "halifax", "st. john",
    # remote tags
    "remote - ca", "remote canada", "remote, canada",
)


def _is_canadian(location_text: str) -> bool:
    if not location_text:
        return False
    t = location_text.lower()
    return any(h in t for h in _CANADA_HINTS)


def _get(url: str) -> dict | list | None:
    for attempt, wait in enumerate(RETRY_BACKOFF, start=1):
        try:
            r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
            if r.status_code == 404:
                log.warning("404 %s", url)
                return None
            if 400 <= r.status_code < 500:
                # 4xx won't be fixed by retrying
                log.warning("%s %s", r.status_code, url)
                return None
            r.raise_for_status()
            return r.json()
        except (requests.RequestException, ValueError) as e:
            log.warning("GET attempt %d/%d failed for %s: %s",
                        attempt, len(RETRY_BACKOFF), url, e)
            if attempt < len(RETRY_BACKOFF):
                time.sleep(wait)
    return None


def _post_json(url: str, body: dict) -> dict | None:
    for attempt, wait in enumerate(RETRY_BACKOFF, start=1):
        try:
            r = requests.post(
                url,
                json=body,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
                timeout=TIMEOUT,
            )
            if r.status_code == 404:
                log.warning("404 %s", url)
                return None
            if 400 <= r.status_code < 500:
                # 4xx: the request is wrong; retrying won't help.
                log.warning("%s %s (body rejected) -- check tenant/host/site",
                            r.status_code, url)
                return None
            r.raise_for_status()
            return r.json()
        except (requests.RequestException, ValueError) as e:
            log.warning("POST attempt %d failed for %s: %s", attempt, url, e)
            if attempt < len(RETRY_BACKOFF):
                time.sleep(wait)
    return None


def fetch_greenhouse(slug: str) -> List[Job]:
    url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"
    data = _get(url)
    if not data or "jobs" not in data:
        return []
    out: List[Job] = []
    for j in data["jobs"]:
        out.append(Job(
            source="greenhouse",
            company=slug,
            job_id=str(j.get("id", "")),
            title=j.get("title", ""),
            location=(j.get("location") or {}).get("name", ""),
            department=", ".join(d.get("name", "") for d in j.get("departments", [])),
            url=j.get("absolute_url", ""),
            description_html=j.get("content", ""),
            posted_at=j.get("updated_at", ""),
        ))
    return out


def fetch_ashby(slug: str) -> List[Job]:
    url = f"https://api.ashbyhq.com/posting-api/job-board/{slug}"
    data = _get(url)
    if not data or "jobs" not in data:
        return []
    out: List[Job] = []
    for j in data["jobs"]:
        out.append(Job(
            source="ashby",
            company=slug,
            job_id=str(j.get("id", "")),
            title=j.get("title", ""),
            location=j.get("location", ""),
            department=j.get("department", ""),
            url=j.get("jobUrl", ""),
            description_html=j.get("descriptionHtml", "") or j.get("description", ""),
            posted_at=j.get("publishedAt", ""),
        ))
    return out


def fetch_lever(slug: str) -> List[Job]:
    url = f"https://api.lever.co/v0/postings/{slug}?mode=json"
    data = _get(url)
    if not isinstance(data, list):
        return []
    out: List[Job] = []
    for j in data:
        cats = j.get("categories", {}) or {}
        out.append(Job(
            source="lever",
            company=slug,
            job_id=str(j.get("id", "")),
            title=j.get("text", ""),
            location=cats.get("location", ""),
            department=cats.get("team", "") or cats.get("department", ""),
            url=j.get("hostedUrl", ""),
            description_html=j.get("descriptionPlain", "") or j.get("description", ""),
            posted_at=str(j.get("createdAt", "")),
        ))
    return out


def fetch_workday(entry: dict) -> List[Job]:
    """Workday CXS API. Requires {tenant, host, site} in the config entry.

    We never send an "applied facet" for country -- Workday rejects the
    request (HTTP 422) unless facets use per-tenant internal IDs. Instead,
    we fetch everything and filter client-side via `country` / `canada_only`.

    To find tenant/host/site for any Workday careers page:
      1. Open the careers site in a browser.
      2. Open DevTools -> Network tab, filter "jobs".
      3. Look for a POST to /wday/cxs/<tenant>/<site>/jobs -- copy those three.
    """
    tenant = entry.get("tenant")
    host = entry.get("host")
    site = entry.get("site")
    keyword = entry.get("keyword", "")
    canada_only = bool(entry.get("country", "")) or bool(entry.get("canada_only", False))

    if not (tenant and host and site):
        log.warning("workday entry missing tenant/host/site: %s", entry)
        return []

    api = f"https://{host}/wday/cxs/{tenant}/{site}/jobs"
    detail_base = f"https://{host}/wday/cxs/{tenant}/{site}"

    out: List[Job] = []
    offset = 0
    page = 50
    while True:
        body: dict = {
            "appliedFacets": {},     # intentionally empty -- see docstring
            "limit": page,
            "offset": offset,
            "searchText": keyword,
        }
        data = _post_json(api, body)
        if not data:
            break
        postings = data.get("jobPostings", []) or []
        if not postings:
            break

        for j in postings:
            location_text = j.get("locationsText", "")
            if canada_only and not _is_canadian(location_text):
                continue
            ext_path = j.get("externalPath", "")
            url = f"https://{host}{ext_path}" if ext_path.startswith("/") else ext_path
            out.append(Job(
                source="workday",
                company=tenant,
                job_id=str(j.get("bulletFields", [""])[0] or ext_path.rsplit("/", 1)[-1]),
                title=j.get("title", ""),
                location=location_text,
                department=j.get("subtitles", [""])[0] if j.get("subtitles") else "",
                url=url,
                description_html=j.get("shortDescription", ""),
                posted_at=j.get("postedOn", ""),
            ))

        total = data.get("total", 0)
        offset += page
        if offset >= total or len(postings) < page:
            break

    # Workday's list endpoint omits full descriptions; pull them on demand
    # for the top N (needed so the matcher has real JD text to work with).
    fetch_descriptions = entry.get("fetch_descriptions", False)
    if fetch_descriptions:
        for job in out[: int(entry.get("descriptions_limit", 25))]:
            ext = urlparse(job.url).path
            d = _get(f"{detail_base}{ext}")
            if d and isinstance(d, dict):
                jp = d.get("jobPostingInfo", {}) or {}
                job.description_html = jp.get("jobDescription", job.description_html)
    return out


_DISPATCH = {
    "greenhouse": lambda e: fetch_greenhouse(e["slug"]),
    "ashby":      lambda e: fetch_ashby(e["slug"]),
    "lever":      lambda e: fetch_lever(e["slug"]),
    "workday":    fetch_workday,
}


def scan_companies(companies: Iterable[dict]) -> List[Job]:
    """Iterate config entries and return all jobs."""
    jobs: List[Job] = []
    for entry in companies:
        board = entry.get("board")
        fn = _DISPATCH.get(board)
        if not fn:
            log.warning("skipping unknown board: %s", entry)
            continue
        try:
            log.info("fetching %s/%s", board, entry.get("slug") or entry.get("tenant"))
            before = len(jobs)
            jobs.extend(fn(entry))
            log.info("  -> %d jobs", len(jobs) - before)
        except Exception as e:
            log.warning("fetch failed for %s: %s", entry, e)
    return jobs


def resolve_single_url(url: str) -> Job | None:
    p = urlparse(url)
    host = p.netloc.lower()
    if "greenhouse.io" in host:
        parts = [x for x in p.path.split("/") if x]
        if len(parts) >= 3 and parts[-2] == "jobs":
            slug, jid = parts[0], parts[-1]
            for j in fetch_greenhouse(slug):
                if j.job_id == jid:
                    return j
    if "ashbyhq.com" in host:
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
    if "myworkdayjobs.com" in host:
        log.info("workday single-URL resolve: run a full scan for that tenant, then use --job-id")
    return None
