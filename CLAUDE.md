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
```

## Running Tests

```bash
# Create venv and install deps
uv venv && uv pip install -e ".[dev]" && uv pip install pytest

# Run tests
python -m pytest tests/test_utils.py -v
```

CI runs tests via tox across Python 3.10-3.14.

## Testing Rules

1. **Use real-world PDFs** from issues as test assets, not synthetic/generated PDFs.
2. **Use the venv python** (`.venv/bin/python`) when running commands.

## Coding Rules

1. **Commits**: Follow conventional commit format: `type(scope): message`
2. **Style**: Ruff is configured in pyproject.toml (line-length 79)
3. **Dependencies**: Use `uv` for dependency management
4. **Changelog**: Every PR MUST include an update to `CHANGES.md`. Add entries under the "Upcoming Changes" section. CI will fail without this.
5. **Comments**: Write thorough comments explaining *why* code exists, not just *what* it does. PDF rendering is full of non-obvious edge cases (rendering artifacts, color space quirks, winding rules, etc.) and future contributors need to understand the reasoning behind each check. Explain the failure mode that motivated the code.
