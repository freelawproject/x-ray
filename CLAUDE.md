# X-Ray Development Guidelines

X-Ray is a library and microservice to find bad redactions in PDFs, maintained by Free Law Project.

## Project Structure

```
xray/                   # Main package
├── __init__.py         # Public API: inspect(), cli()
├── pdf_utils.py        # Core detection logic (rectangles, annotations, pixmaps)
├── text_utils.py       # Text filtering and validation
└── custom_types.py     # Type definitions
tests/
├── test_utils.py       # Test suite
└── assets/             # Test PDF files
tools/                  # Developer utilities for investigating PDFs
├── layout-analyzer.py  # Visualize page layout (text blocks, images, CropBox)
├── quick-inspect.py    # Run xray.inspect() and print results
├── inspect-pdf.py      # Dump redaction-relevant PDF structure (drawings, colors, annotations)
└── debug-pipeline.py   # Step through x-ray's detection pipeline showing kept/dropped at each stage
```

## Debugging Tools

When investigating a PDF, use the tools in `tools/` before writing ad-hoc scripts:

```bash
# What does x-ray currently detect?
.venv/bin/python tools/quick-inspect.py some.pdf

# What does this PDF look like structurally?
.venv/bin/python tools/inspect-pdf.py some.pdf --page 0

# Where in the pipeline does detection fail or succeed?
.venv/bin/python tools/debug-pipeline.py some.pdf --page 0
```

`inspect-pdf.py` shows the raw PDF structure: fill colors, drawing types (`re` vs lines+curves), annotations, and text spans. Use it first to understand what's in the PDF.

`debug-pipeline.py` runs the actual x-ray detection pipeline step by step, showing counts at each stage and color analysis for pixmap-filtered entries. Use it to pinpoint exactly where detection fails.

## Running Tests

```bash
# Create venv and install deps (including pytest, mypy, pre-commit)
uv sync --group dev

# Run tests
.venv/bin/python -m pytest tests/test_utils.py -v
```

CI runs tests via tox across Python 3.10-3.14.

## Testing Rules

1. **Use real-world PDFs** from issues as test assets, not synthetic/generated PDFs.
2. **Use the venv python** (`.venv/bin/python`) when running commands.

## Pre-commit and Linting

Before committing, run pre-commit and mypy to catch issues early. The git hooks will run pre-commit automatically, but running them manually first avoids failed commits:

```bash
.venv/bin/python -m pre_commit run --all-files
uv run mypy .
```

CI runs both of these — if either fails, the PR will not pass.

## Coding Rules

1. **Commits**: Follow conventional commit format: `type(scope): message`
2. **Style**: Ruff is configured in pyproject.toml (line-length 79)
3. **Dependencies**: Use `uv` for dependency management
4. **Changelog**: Every PR MUST include an update to `CHANGES.md`. Add entries under the "Upcoming Changes" section. CI will fail without this.
5. **Comments**: Write thorough comments explaining *why* code exists, not just *what* it does. PDF rendering is full of non-obvious edge cases (rendering artifacts, color space quirks, winding rules, etc.) and future contributors need to understand the reasoning behind each check. Explain the failure mode that motivated the code.
6. **No inline imports**: All imports MUST be at the top of the file. Never use `import` inside a function or method.
