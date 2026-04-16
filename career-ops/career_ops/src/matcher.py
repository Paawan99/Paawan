"""Keyword extraction, resume/JD overlap scoring, and recency filtering."""

from __future__ import annotations

import html
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Dict, Iterable, List, Set

from .models import Job, MatchReport

_TAG = re.compile(r"<[^>]+>")
_WORD = re.compile(r"[A-Za-z][A-Za-z0-9+.#\-]{1,}")

_STOPWORDS: Set[str] = {
    "a", "an", "and", "or", "but", "the", "of", "in", "on", "at", "to",
    "for", "with", "by", "from", "as", "is", "are", "was", "were", "be",
    "been", "being", "this", "that", "these", "those", "it", "its", "we",
    "you", "your", "our", "us", "they", "them", "their", "have", "has",
    "had", "do", "does", "did", "will", "would", "should", "can", "could",
    "may", "might", "must", "shall", "not", "no", "yes", "if", "then",
    "else", "than", "so", "such", "any", "all", "some", "every", "each",
    "more", "most", "other", "into", "about", "over", "under", "between",
    "team", "teams", "work", "working", "experience", "years", "year",
    "job", "role", "position", "company", "candidate", "candidates",
    "responsibilities", "qualifications", "requirements", "preferred",
    "nice", "etc", "via", "across", "while", "during", "based", "include",
    "includes", "including", "ability", "able", "strong", "good", "great",
}


def _strip_html(s: str) -> str:
    return html.unescape(_TAG.sub(" ", s or ""))


def tokenize(text: str) -> List[str]:
    clean = _strip_html(text).lower()
    return [t for t in _WORD.findall(clean) if t not in _STOPWORDS and len(t) > 1]


def extract_keywords(text: str, top_n: int = 40) -> List[str]:
    counts = Counter(tokenize(text))
    return [tok for tok, _ in counts.most_common(top_n)]


def _profile_terms(profile: dict) -> Dict[str, float]:
    weights = {"must_have": 3.0, "strong": 2.0, "familiar": 1.0}
    out: Dict[str, float] = {}
    skills = (profile or {}).get("skills", {}) or {}
    for bucket, terms in skills.items():
        w = weights.get(bucket, 1.0)
        for t in terms or []:
            out[t.lower().strip()] = max(out.get(t.lower().strip(), 0), w)
    for t in (profile or {}).get("target_titles", []) or []:
        for tok in tokenize(t):
            out.setdefault(tok, 1.5)
    return out


def _score(profile_terms: Dict[str, float], jd_tokens: List[str]) -> float:
    if not jd_tokens:
        return 0.0
    jd_set = set(jd_tokens)
    hit_weight = sum(w for term, w in profile_terms.items() if term in jd_set)
    max_possible = sum(profile_terms.values()) or 1.0
    return round(min(100.0, 100.0 * hit_weight / max_possible), 1)


def match_job(job: Job, profile: dict) -> MatchReport:
    jd_tokens = tokenize(job.title + " " + job.description_html)
    jd_set = set(jd_tokens)
    profile_terms = _profile_terms(profile)

    matched = sorted({t for t in profile_terms if t in jd_set})
    counts = Counter(jd_tokens)
    missing = [tok for tok, _ in counts.most_common(50) if tok not in profile_terms][:15]

    score = _score(profile_terms, jd_tokens)
    return MatchReport(
        job=job,
        score=score,
        matched_keywords=matched,
        missing_keywords=missing,
    )


def match_all(jobs: Iterable[Job], profile: dict, min_score: float = 0.0) -> List[MatchReport]:
    reports = [match_job(j, profile) for j in jobs]
    reports = [r for r in reports if r.score >= min_score]
    reports.sort(key=lambda r: r.score, reverse=True)
    return reports


def filter_excluded(jobs: Iterable[Job], profile: dict) -> List[Job]:
    excludes = [t.lower() for t in (profile or {}).get("exclude_titles", []) or []]
    if not excludes:
        return list(jobs)
    out = []
    for j in jobs:
        title_lc = (j.title or "").lower()
        if any(ex in title_lc for ex in excludes):
            continue
        out.append(j)
    return out


# ---------------------------------------------------------------------------
# Recency filter (e.g. "postings in the last 7 days")
# ---------------------------------------------------------------------------

_RE_N_DAYS = re.compile(r"posted\s*(\d+)\+?\s*days?\s*ago", re.IGNORECASE)
_RE_N_HOURS = re.compile(r"posted\s*(\d+)\+?\s*hours?\s*ago", re.IGNORECASE)
_RE_N_WEEKS = re.compile(r"posted\s*(\d+)\+?\s*weeks?\s*ago", re.IGNORECASE)
_RE_N_MONTHS = re.compile(r"posted\s*(\d+)\+?\s*months?\s*ago", re.IGNORECASE)


def _parse_posted(posted_at: str) -> datetime | None:
    """Best-effort parse of a posted_at field across boards.

    Supports:
      - ISO 8601 strings (Greenhouse, Ashby)
      - Unix ms timestamps (Lever, as a stringified int)
      - Workday phrases: "Today", "Yesterday", "Posted N Days Ago", etc.
    Returns a UTC datetime, or None if unparseable.
    """
    if not posted_at:
        return None
    s = str(posted_at).strip()
    low = s.lower()
    now = datetime.now(timezone.utc)

    if "today" in low or "just posted" in low:
        return now
    if "yesterday" in low:
        return now - timedelta(days=1)

    m = _RE_N_HOURS.search(low)
    if m:
        return now - timedelta(hours=int(m.group(1)))
    m = _RE_N_DAYS.search(low)
    if m:
        return now - timedelta(days=int(m.group(1)))
    m = _RE_N_WEEKS.search(low)
    if m:
        return now - timedelta(weeks=int(m.group(1)))
    m = _RE_N_MONTHS.search(low)
    if m:
        return now - timedelta(days=30 * int(m.group(1)))

    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        pass

    try:
        ts = int(s)
        # Lever returns ms; anything > ~1e12 is clearly ms, not seconds.
        if ts > 10_000_000_000:
            return datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
        return datetime.fromtimestamp(ts, tz=timezone.utc)
    except (TypeError, ValueError):
        pass
    return None


def filter_since_days(jobs: Iterable[Job], days: int, keep_unknown: bool = True) -> List[Job]:
    """Drop jobs posted more than `days` ago.

    If keep_unknown is True, postings whose posted_at can't be parsed are
    kept (safer default -- banks' Workday feeds often omit exact dates).
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    out: List[Job] = []
    for j in jobs:
        dt = _parse_posted(j.posted_at)
        if dt is None:
            if keep_unknown:
                out.append(j)
            continue
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        if dt >= cutoff:
            out.append(j)
    return out
