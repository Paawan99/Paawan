# career-ops

AI-assisted job search + resume tailoring pipeline for Paawan.

Inspired by [santifer/career-ops](https://github.com/santifer/career-ops): this is a smaller,
opinionated version that does the job-match and resume-tailoring loop end-to-end.

## What it does

1. **Scan** public company job boards (Greenhouse, Ashby, Lever) for openings
   matching your `profile.yaml` (roles, keywords, locations).
2. **Match** any job description against your resume keywords — reports
   overlap %, the matched keywords, and the ones that are missing.
3. **Tailor** your resume (either a committed `resume.docx` or a markdown
   CV template) by injecting profile-approved keywords into the Skills /
   Summary sections.
4. **Export** the tailored resume to both `.docx` and `.pdf`.
5. **Apply** — prints the job's direct application URL and the path to the
   tailored PDF you can upload there.

## Quick start

```bash
# 1. Install deps
python -m pip install -r career_ops/requirements.txt

# 2. Copy the example profile and fill in your details
cp career_ops/config/profile.yaml.example career_ops/config/profile.yaml
$EDITOR career_ops/config/profile.yaml

# 3. Drop your resume in (either or both)
cp ~/Documents/my_resume.docx career_ops/resume/resume.docx
# and/or edit the markdown template:
$EDITOR career_ops/templates/cv_markdown.md

# 4. Scan boards for matches
python -m career_ops.src.cli scan

# 5. Score any specific job
python -m career_ops.src.cli match "https://boards.greenhouse.io/anthropic/jobs/1234567"

# 6. Tailor + export
python -m career_ops.src.cli tailor "https://boards.greenhouse.io/anthropic/jobs/1234567"

# 7. Get the apply link + file path
python -m career_ops.src.cli apply "https://boards.greenhouse.io/anthropic/jobs/1234567"
```

## Layout

```
career_ops/
  config/
    profile.yaml.example     your skills, target roles, keyword dictionary
    companies.yaml           companies + their board (greenhouse/ashby/lever)
  resume/
    resume.docx              your master Word resume (gitignored)
  templates/
    cv_markdown.md           santifer-style CV template (Jinja2)
  src/
    cli.py                   entry point (scan/match/tailor/apply)
    scraper.py               Greenhouse/Ashby/Lever public JSON APIs
    matcher.py               keyword extraction + overlap scoring
    resume_tailor.py         python-docx manipulation
    cv_renderer.py           markdown -> HTML -> PDF
    exporter.py              docx -> pdf via libreoffice
    models.py                dataclasses: Job, MatchReport, Profile
  output/                    tailored resumes land here (gitignored)
  tests/
    test_matcher.py
```

## Apply flow (why no auto-submit)

Most job portals (LinkedIn, Greenhouse, Ashby, Lever) forbid programmatic
application submissions and use anti-bot protections. So the `apply` command
does the realistic thing:

1. Generates the tailored resume PDF at a known path.
2. Prints the application URL.
3. Copies the PDF path to your clipboard (if `xclip`/`pbcopy` available).

You click the link, open the portal's native apply form, and upload the PDF.
This keeps you inside the portal's ToS and avoids the fragility of browser
automation.
