"""Tests for the matcher module.

Run with: pytest career-ops/career_ops/tests/
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow `from src.matcher import ...` whether run from repo root or career-ops/
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.matcher import (  # noqa: E402
    extract_keywords,
    filter_excluded,
    match_job,
    tokenize,
)
from src.models import Job  # noqa: E402


PROFILE = {
    "skills": {
        "must_have": ["python", "docker"],
        "strong": ["aws", "postgres"],
        "familiar": ["rust"],
    },
    "target_titles": ["Backend Engineer"],
    "exclude_titles": ["intern", "manager"],
}


def _job(title: str, desc: str = "") -> Job:
    return Job(
        source="greenhouse",
        company="acme",
        job_id="1",
        title=title,
        location="Remote",
        department="Eng",
        url="https://example.com/1",
        description_html=desc,
        posted_at="",
    )


def test_tokenize_drops_stopwords_and_html():
    text = "<p>The Python and Docker stack is great</p>"
    toks = tokenize(text)
    assert "python" in toks
    assert "docker" in toks
    assert "the" not in toks
    assert "and" not in toks
    assert "<p>" not in " ".join(toks)


def test_extract_keywords_top_n():
    text = "python " * 5 + "docker " * 3 + "aws " * 1
    kws = extract_keywords(text, top_n=2)
    assert kws[:2] == ["python", "docker"]


def test_match_job_finds_overlap():
    jd = "Looking for a Python engineer with Docker and AWS experience."
    report = match_job(_job("Backend Engineer", jd), PROFILE)
    assert "python" in report.matched_keywords
    assert "docker" in report.matched_keywords
    assert "aws" in report.matched_keywords
    assert report.score > 0


def test_match_job_zero_when_no_overlap():
    jd = "We need a Salesforce admin with Visualforce experience."
    report = match_job(_job("Salesforce Admin", jd), PROFILE)
    # may have ~0 because none of must_have/strong terms appear
    assert report.score < 20


def test_filter_excluded_drops_intern_and_manager():
    jobs = [
        _job("Software Engineer Intern"),
        _job("Engineering Manager"),
        _job("Backend Engineer"),
    ]
    kept = filter_excluded(jobs, PROFILE)
    assert len(kept) == 1
    assert kept[0].title == "Backend Engineer"


def test_missing_keywords_excludes_profile_terms():
    jd = "Need Kubernetes and Kafka experience plus Python."
    report = match_job(_job("Backend Engineer", jd), PROFILE)
    assert "python" not in report.missing_keywords  # in profile
    # at least one of the unfamiliar terms should surface
    assert any(k in report.missing_keywords for k in ("kubernetes", "kafka"))
