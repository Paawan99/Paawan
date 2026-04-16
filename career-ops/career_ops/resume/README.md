# Resume drop folder

Put your master resume here as **`resume.docx`**. It will be read by
`resume_tailor.py`, which makes a tailored copy for each job under
`../output/<job-slug>/resume.docx` — **your master is never modified**.

For the tailor to find where to inject keywords, the docx needs to have a
heading named one of:
- `Skills` / `Core Skills` / `Technical Skills` / `Key Skills`
- `Summary` / `Professional Summary` / `About` / `Profile`

(Heading detection is flexible — Word's built-in "Heading 1/2/3" styles work,
or a bold standalone line.)

If you'd rather not use a docx, leave this folder empty and use the markdown
CV template at `../templates/cv_markdown.md`. Run tailor with
`--use-template` to render a PDF directly from that.

> **Note:** `resume.docx` is gitignored so your personal document never gets
> pushed to GitHub.
