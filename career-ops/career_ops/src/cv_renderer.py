"""Render a CV from structured profile data via a Jinja2 markdown template.

This is the santifer/career-ops style: keep the CV as data + a template,
generate markdown / HTML / PDF on demand. It's an alternative to editing
a hand-maintained .docx.

All template/PDF deps are loaded lazily so the rest of the CLI does not
require them at import time.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import List

log = logging.getLogger(__name__)

DEFAULT_TEMPLATE = Path(__file__).resolve().parent.parent / "templates" / "cv_markdown.md"


def render_markdown(profile: dict, extra_skills: List[str] | None = None,
                    template_path: str | Path | None = None) -> str:
    """Render the CV as markdown. No external deps beyond jinja2."""
    try:
        from jinja2 import Template  # type: ignore
    except ImportError as e:
        raise RuntimeError(
            "jinja2 is required for render_markdown. Install: pip install jinja2"
        ) from e

    tpl_path = Path(template_path) if template_path else DEFAULT_TEMPLATE
    tpl_text = tpl_path.read_text(encoding="utf-8")
    return Template(tpl_text).render(
        profile=profile,
        extra_skills=extra_skills or [],
    )


def render_html(profile: dict, extra_skills: List[str] | None = None,
                template_path: str | Path | None = None) -> str:
    try:
        import markdown as md  # type: ignore
    except ImportError as e:
        raise RuntimeError(
            "markdown is required for render_html. Install: pip install markdown"
        ) from e

    body = md.markdown(
        render_markdown(profile, extra_skills, template_path),
        extensions=["extra", "sane_lists"],
    )
    return f"""<!doctype html><html><head><meta charset="utf-8">
<style>
body {{ font-family: -apple-system, system-ui, sans-serif; max-width: 760px;
        margin: 2em auto; line-height: 1.4; color: #222; }}
h1 {{ margin-bottom: 0; }}
h2 {{ border-bottom: 1px solid #ccc; padding-bottom: 4px; margin-top: 1.5em; }}
ul {{ margin-top: 0.2em; }}
</style></head><body>
{body}
</body></html>"""


def render_pdf(profile: dict, output_path: str | Path,
               extra_skills: List[str] | None = None,
               template_path: str | Path | None = None) -> Path:
    try:
        from weasyprint import HTML  # type: ignore
    except ImportError as e:
        raise RuntimeError(
            "weasyprint is required for render_pdf. Install: pip install weasyprint"
        ) from e

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    html = render_html(profile, extra_skills, template_path)
    HTML(string=html).write_pdf(str(output_path))
    return output_path
