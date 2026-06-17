from pathlib import Path

import pytest

from tests import ASSETS


@pytest.fixture(scope="session")
def assets_dir() -> Path:
    return ASSETS


BENCHMARK_ASSETS = [
    pytest.param(p, id=p.name) for p in sorted(ASSETS.glob("*.pdf"))
]
