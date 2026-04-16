"""Exporters: docx -> pdf, and match reports -> CSV.

The PDF export shells out to LibreOffice headless. Reasons:
- works on Linux/macOS without per-platform deps
- preserves the .docx layout exactly (unlike a re-render)
- no licensing issues

If libreoffice isn't installed, we surface a clear error instead of
silently failing.
"""

from __future__ import annotations

import csv
import logging
import shutil
import subprocess
from pathlib import Path
from typing import Iterable

from .models import MatchReport

log = logging.getLogger(__name__)


def docx_to_pdf(docx_path: str | Path, output_dir: str | Path | None = None) -> Path:
    docx_path = Path(docx_path)
    if not docx_path.exists():
        raise FileNotFoundError(docx_path)
    out_dir = Path(output_dir) if output_dir else docx_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)

    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        raise RuntimeError(
            "LibreOffice not found. Install it (brew install libreoffice / "
            "apt install libreoffice) to enable PDF export."
        )

    cmd = [
        soffice, "--headless", "--convert-to", "pdf",
        "--outdir", str(out_dir), str(docx_path),
    ]
    log.info("running: %s", " ".join(cmd))
    subprocess.run(cmd, check=True, capture_output=True)
    pdf_path = out_dir / (docx_path.stem + ".pdf")
    if not pdf_path.exists():
        raise RuntimeError(f"expected {pdf_path} but it wasn't produced")
    return pdf_path


def write_matches_csv(reports: Iterable[MatchReport], output_path: str | Path) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "score", "company", "title", "location", "source",
            "url", "matched", "missing",
        ])
        for r in reports:
            w.writerow([
                r.score,
                r.job.company,
                r.job.title,
                r.job.location,
                r.job.source,
                r.job.url,
                "; ".join(r.matched_keywords),
                "; ".join(r.missing_keywords),
            ])
    return output_path
