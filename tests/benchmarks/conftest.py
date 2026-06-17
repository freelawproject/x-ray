from pathlib import Path

import fitz
import pytest

ASSETS = Path(__file__).resolve().parents[1] / "assets"


@pytest.fixture(scope="session")
def bad_redaction_path() -> Path:
    return ASSETS / "rectangles_yes.pdf"


@pytest.fixture(scope="session")
def bad_redaction_bytes(bad_redaction_path: Path) -> bytes:
    return bad_redaction_path.read_bytes()


@pytest.fixture(scope="session")
def tricky_clean_path() -> Path:
    return ASSETS / "no_bad_redactions.5.5.pdf"


@pytest.fixture(scope="session")
def expected_redaction_text() -> list[str]:
    return [
        "“No”",
        "“Yes”, but did not disclose all relevant medical history",
        "“No”",
    ]


@pytest.fixture
def bad_redaction_page(bad_redaction_path: Path):
    with fitz.open(bad_redaction_path) as pdf:
        yield pdf[0]


@pytest.fixture
def tricky_clean_page(tricky_clean_path: Path):
    with fitz.open(tricky_clean_path) as pdf:
        yield pdf[4]
