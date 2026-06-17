from pathlib import Path

import pytest

import xray
from tests.conftest import BENCHMARK_ASSETS


@pytest.mark.parametrize("pdf", BENCHMARK_ASSETS)
def test_inspect(benchmark, pdf: Path):
    benchmark(xray.inspect, pdf)
