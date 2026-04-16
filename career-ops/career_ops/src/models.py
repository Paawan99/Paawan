"""Shared dataclasses used across scraper / matcher / tailor."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Job:
    """A single posting pulled from a company board."""

    company: str
    title: str
    location: str
    description: str  # plain text; HTML stripped by the scraper
    apply_url: str
    board: str  # greenhouse | ashby | lever
    external_id: str = ""

    @property
    def slug(self) -> str:
        """Filesystem-safe identifier for output artifacts."""
        raw = f"{self.company}-{self.title}-{self.external_id}"
        return "".join(c if c.isalnum() or c in "-_" else "-" for c in raw).lower()[:80]


@dataclass
class MatchReport:
    """Result of scoring a Job against a Profile."""

    job: Job
    score: float  # 0..100
    matched_keywords: List[str] = field(default_factory=list)
    missing_keywords: List[str] = field(default_factory=list)
    title_match: bool = False
    location_match: bool = False
    excluded: bool = False  # hit a profile.exclude_titles term

    def summary_line(self) -> str:
        flag = "X" if self.excluded else ("*" if self.score >= 70 else " ")
        return (
            f"[{flag}] {self.score:5.1f}  {self.job.company:<20}  "
            f"{self.job.title[:50]:<50}  {self.job.location[:30]}"
        )
