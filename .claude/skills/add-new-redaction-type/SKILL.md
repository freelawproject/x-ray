---
name: add-new-redaction-type
description: Add a new redaction detection type to x-ray. Downloads a test PDF, analyzes it, writes a fix and test, runs the test suite, and updates the changelog.
---

You are working on x-ray, a library that detects bad redactions in PDFs.

## Step 1: Gather information

Ask the user for the following (skip anything they already provided):

- **PDF URL** — a link to a PDF that demonstrates the issue
- **Test asset name** — a short snake_case name for the PDF (e.g., `white_on_white`)
- **Problem description** — what's wrong with current detection (false positive? missed redaction? new pattern?)
- **GitHub issue number** (optional) — for linking in the changelog

## Step 2: Download the PDF

Save it to `tests/assets/<name>.pdf` using curl. If the file exceeds 5MB (pre-commit will reject it), use `tools/trim-pdf.py` to extract only the relevant pages.

## Step 3: Analyze the PDF

Use `.venv/bin/python` for all commands.

1. Run `tools/quick-inspect.py` to see what x-ray currently detects
2. Run `tools/inspect-pdf.py` to dump the PDF structure (drawings, fill colors, item types, annotations, text spans)
3. Run `tools/debug-pipeline.py` to walk through the detection pipeline and see what gets kept/dropped at each stage with pixmap color analysis
4. If the tools don't provide enough detail, use PyMuPDF (`fitz`) directly for deeper investigation
5. Explain findings to the user before proceeding

## Step 4: Write the fix

Modify the detection pipeline. Key files:
- `xray/pdf_utils.py` — rectangle detection, intersection logic, pixmap filtering, annotation detection
- `xray/text_utils.py` — text filtering and validation

Read the relevant files before making changes. Follow existing patterns.

## Step 5: Write the test

Add a test method to `IntegrationTest` in `tests/test_utils.py`. Follow the existing pattern:

```python
def test_<name>_no_results(self):
    """<Description>"""
    path = root_path / "<name>.pdf"
    redactions = xray.inspect(path)
    self.assertEqual(
        redactions,
        {},
        msg="<failure message>",
    )
```

Adjust assertions based on whether the fix is about eliminating false positives (expect `{}`) or detecting new bad redactions (expect specific results).

## Step 6: Run tests

```bash
.venv/bin/python -m pytest tests/test_utils.py -v
```

All tests must pass. If they don't, fix the issue and re-run.

## Step 7: Update changelog

Add an entry under "Upcoming Changes" in `CHANGES.md`. If a GitHub issue number was provided, link it:

```
 - Description of the change ([issue](https://github.com/freelawproject/x-ray/issues/NUMBER))
```

If no issue number, just add the description without the link.

## Done

Tell the user the fix is ready and they can use `/shipit` to branch, commit, and create a PR.
