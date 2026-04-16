"""Keyword extraction and resume/JD overlap scoring.

Approach:
- Tokenize the JD, lowercase, strip HTML, drop a stopword list.
- Score = weighted overlap between JD tokens and the candidate's profile
  skills (which are categorized: must_have, strong, familiar).
- Report missing keywords (in JD but not in profile) so the tailor module
  can decide whether to surface them.

This is intentionally simple — no embeddings, no ML — so the tool stays
hackable and offline-friendly. Upgrade path: swap `_score` for a sentence
embedding cosine if you want.
"""

from __future__ import annotations

import html
import re
from collections import Counter
from typing import Dict, Iterable, List, Set

from .models import Job, MatchReport

_TAG = re.compile(r"<[^>]+>")
_WORD = re.compile(r"[A-Za-z][A-Za-z0-9+.#\-]{1,}")

# kept tiny on purpose — lots of "skills" are actually short tokens.
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
    """Lowercase tokens, stopwords removed, HTML stripped."""
    clean = _strip_html(text).lower()
    return [t for t in _WORD.findall(clean) if t not in _STOPWORDS and len(t) > 1]


def extract_keywords(text: str, top_n: int = 40) -> List[str]:
    """Top-N tokens by frequency. Useful for showing what a JD emphasizes."""
    counts = Counter(tokenize(text))
    return [tok for tok, _ in counts.most_common(top_n)]


def _profile_terms(profile: dict) -> Dict[str, float]:
    """Flatten profile.skills into {term: weight}.

    Profile shape (see config/profile.yaml.example):
        skills:
          must_have: [python, ...]
          strong:    [docker, ...]
          familiar:  [rust, ...]
    """
    weights = {"must_have": 3.0, "strong": 2.0, "familiar": 1.0}
    out: Dict[str, float] = {}
    skills = (profile or {}).get("skills", {}) or {}
    for bucket, terms in skills.items():
        w = weights.get(bucket, 1.0)
        for t in terms or []:
            out[t.lower().strip()] = max(out.get(t.lower().strip(), 0), w)
    # also fold in titles the candidate is targeting
    for t in (profile or {}).get("target_titles", []) or []:
        for tok in tokenize(t):
            out.setdefault(tok, 1.5)
    return out


def _score(profile_terms: Dict[str, float], jd_tokens: List[str]) -> float:
    """Return 0..100. Weighted profile-hits over JD-token-volume."""
    if not jd_tokens:
        return 0.0
    jd_set = set(jd_tokens)
    hit_weight = sum(w for term, w in profile_terms.items() if term in jd_set)
    # normalize against a constant so scores are comparable across JDs
    # (long JDs would otherwise look weaker than short ones).
    max_possible = sum(profile_terms.values()) or 1.0
    return round(min(100.0, 100.0 * hit_weight / max_possible), 1)


def match_job(job: Job, profile: dict) -> MatchReport:
    jd_tokens = tokenize(job.title + " " + job.description_html)
    jd_set = set(jd_tokens)
    profile_terms = _profile_terms(profile)

    matched = sorted({t for t in profile_terms if t in jd_set})
    # candidate "missing" pool = high-frequency JD tokens that aren't in profile
    counts = Counter(jd_tokens)
    missing = [
        tok for tok, _ in counts.most_common(50)
        if tok not in profile_terms
    ][:15]

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
    """Drop jobs whose title contains any token from profile.exclude_titles."""
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
