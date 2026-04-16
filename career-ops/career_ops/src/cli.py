"""career-ops CLI: scan -> match -> tailor -> apply.

Subcommands:
  scan    fetch all jobs listed in companies.yaml -> output/jobs.json
  match   score scanned jobs against profile.yaml -> output/matches.csv
  tailor  generate a tailored .docx (and optional PDF) for one match
  apply   print the application URL + the tailored resume path
  render  render a CV from profile only (santifer-style, no source .docx)

This module imports heavy/optional deps lazily inside each subcommand
so `--help` and unrelated commands work even on a minimal install.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PROFILE = ROOT / "config" / "profile.yaml"
DEFAULT_COMPANIES = ROOT / "config" / "companies.yaml"
DEFAULT_OUTPUT = ROOT / "output"


def _load_yaml(path: Path) -> dict | list:
    try:
        import yaml  # type: ignore
    except ImportError:
        sys.exit("PyYAML is required. Install: pip install pyyaml")
    if not path.exists():
        sys.exit(f"missing: {path}")
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )


def cmd_scan(args: argparse.Namespace) -> int:
    from .scraper import scan_companies, resolve_single_url

    DEFAULT_OUTPUT.mkdir(parents=True, exist_ok=True)
    if args.url:
        job = resolve_single_url(args.url)
        if not job:
            print(f"could not resolve {args.url}", file=sys.stderr)
            return 1
        out = [job.to_dict()]
    else:
        companies = _load_yaml(Path(args.companies))
        if isinstance(companies, dict):
            companies = companies.get("companies", [])
        jobs = scan_companies(companies)
        out = [j.to_dict() for j in jobs]

    target = Path(args.output) / "jobs.json"
    target.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"wrote {len(out)} jobs -> {target}")
    return 0


def cmd_match(args: argparse.Namespace) -> int:
    from .matcher import match_all, filter_excluded
    from .models import Job
    from .exporter import write_matches_csv

    profile = _load_yaml(Path(args.profile))
    jobs_file = Path(args.jobs) if args.jobs else Path(args.output) / "jobs.json"
    if not jobs_file.exists():
        sys.exit(f"missing: {jobs_file} — run `scan` first")

    raw = json.loads(jobs_file.read_text(encoding="utf-8"))
    jobs = [Job(**j) for j in raw]
    jobs = filter_excluded(jobs, profile)
    reports = match_all(jobs, profile, min_score=args.min_score)

    csv_path = Path(args.output) / "matches.csv"
    write_matches_csv(reports, csv_path)
    print(f"wrote {len(reports)} matches -> {csv_path}")
    for r in reports[: args.top]:
        print(f"  [{r.score:5.1f}] {r.job.company:18s} {r.job.title}")
    return 0


def _find_match(args: argparse.Namespace):
    """Re-run matching to find the requested job by id or URL."""
    from .matcher import match_all, filter_excluded
    from .models import Job

    profile = _load_yaml(Path(args.profile))
    jobs_file = Path(args.jobs) if args.jobs else Path(args.output) / "jobs.json"
    if not jobs_file.exists():
        sys.exit(f"missing: {jobs_file} — run `scan` first")
    raw = json.loads(jobs_file.read_text(encoding="utf-8"))
    jobs = [Job(**j) for j in raw]
    jobs = filter_excluded(jobs, profile)
    reports = match_all(jobs, profile)

    for r in reports:
        if args.job_id and r.job.job_id == args.job_id:
            return profile, r
        if args.url and r.job.url == args.url:
            return profile, r
    sys.exit("no matching job found (try `match` first or check id/url)")


def cmd_tailor(args: argparse.Namespace) -> int:
    from .resume_tailor import tailor_docx

    profile, report = _find_match(args)
    source = Path(args.source) if args.source else Path(profile.get("resume_docx", ""))
    if not source.exists():
        sys.exit(f"resume source not found: {source}")

    safe_company = "".join(c for c in report.job.company if c.isalnum() or c in "-_")
    safe_title = "".join(c for c in report.job.title if c.isalnum() or c in "-_")[:40]
    out_docx = Path(args.output) / "resumes" / f"{safe_company}_{safe_title}.docx"

    result = tailor_docx(source, out_docx, profile, report.matched_keywords)
    print(f"docx -> {result['output']}")
    print(f"added: {', '.join(result['added']) or '(none)'}")

    if args.pdf:
        from .exporter import docx_to_pdf
        pdf = docx_to_pdf(out_docx)
        print(f"pdf  -> {pdf}")
    return 0


def cmd_apply(args: argparse.Namespace) -> int:
    _, report = _find_match(args)
    safe_company = "".join(c for c in report.job.company if c.isalnum() or c in "-_")
    safe_title = "".join(c for c in report.job.title if c.isalnum() or c in "-_")[:40]
    docx = Path(args.output) / "resumes" / f"{safe_company}_{safe_title}.docx"
    pdf = docx.with_suffix(".pdf")

    print(f"job:    {report.job.title} @ {report.job.company}")
    print(f"score:  {report.score}")
    print(f"apply:  {report.job.url}")
    print(f"resume: {pdf if pdf.exists() else docx}")
    print()
    print("Direct submission isn't supported (most boards forbid it).")
    print("Open the URL above and attach the resume file shown.")
    return 0


def cmd_render(args: argparse.Namespace) -> int:
    from .cv_renderer import render_markdown, render_pdf

    profile = _load_yaml(Path(args.profile))
    md_text = render_markdown(profile)
    md_path = Path(args.output) / "resumes" / "cv.md"
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(md_text, encoding="utf-8")
    print(f"md  -> {md_path}")

    if args.pdf:
        pdf_path = md_path.with_suffix(".pdf")
        render_pdf(profile, pdf_path)
        print(f"pdf -> {pdf_path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="career-ops", description=__doc__)
    p.add_argument("-v", "--verbose", action="store_true")
    p.add_argument("--profile", default=str(DEFAULT_PROFILE))
    p.add_argument("--companies", default=str(DEFAULT_COMPANIES))
    p.add_argument("--output", default=str(DEFAULT_OUTPUT))

    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("scan", help="fetch all configured job listings")
    s.add_argument("--url", help="resolve a single job URL instead of scanning")
    s.set_defaults(func=cmd_scan)

    m = sub.add_parser("match", help="score scanned jobs against profile")
    m.add_argument("--jobs", help="path to jobs.json (default: output/jobs.json)")
    m.add_argument("--min-score", type=float, default=10.0)
    m.add_argument("--top", type=int, default=20)
    m.set_defaults(func=cmd_match)

    t = sub.add_parser("tailor", help="produce a tailored resume for a job")
    t.add_argument("--job-id")
    t.add_argument("--url")
    t.add_argument("--jobs")
    t.add_argument("--source", help="path to source .docx (default: profile.resume_docx)")
    t.add_argument("--pdf", action="store_true")
    t.set_defaults(func=cmd_tailor)

    a = sub.add_parser("apply", help="print the application URL + resume path")
    a.add_argument("--job-id")
    a.add_argument("--url")
    a.add_argument("--jobs")
    a.set_defaults(func=cmd_apply)

    r = sub.add_parser("render", help="render CV from template (no source .docx)")
    r.add_argument("--pdf", action="store_true")
    r.set_defaults(func=cmd_render)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    _setup_logging(args.verbose)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
