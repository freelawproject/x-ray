from pathlib import Path

import pytest

from tests import ASSETS
from tests.reporting import write_benchmark_report


@pytest.fixture(scope="session")
def assets_dir() -> Path:
    return ASSETS


BENCHMARK_ASSETS = [
    pytest.param(p, id=p.name) for p in sorted(ASSETS.glob("*.pdf"))
]


@pytest.hookimpl(trylast=True)
def pytest_sessionfinish(session, exitstatus):
    write_benchmark_report()
