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

## Coding Rules

1. **Commits**: Follow conventional commit format: `type(scope): message`
2. **Style**: Ruff is configured in pyproject.toml (line-length 79)
3. **Dependencies**: Use `uv` for dependency management
4. **Changelog**: Every PR MUST include an update to `CHANGES.md`. Add entries under the "Upcoming Changes" section. CI will fail without this.
