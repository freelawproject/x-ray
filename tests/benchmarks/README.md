# Benchmarks

This directory contains benchmark-related tests:

- `quality/` contains normal pytest tests that verify benchmark fixture
  assumptions and expected results.
- `performance/` contains `pytest-benchmark` tests that time
  performance-sensitive parts of x-ray's PDF redaction analysis.

Benchmarks use the standard `benchmark` fixture pattern:

```python
result = benchmark(function_to_measure, *args, **kwargs)
assert result == expected_result
```

Keep setup outside the benchmarked call when setup is not part of the behavior
being measured. The assertion runs after timing and protects the benchmark from
measuring incorrect behavior.

## Running

Run benchmark quality checks without timing:

```sh
uv run pytest tests/benchmarks/quality
```

Run timed performance benchmarks:

```sh
uv run pytest tests/benchmarks/performance --benchmark-enable
```

Run them with the rest of the pytest suite but without timing:

```sh
uv run pytest --benchmark-disable
```

The existing `python -m unittest` test command does not import these files
because benchmark modules use the `benchmark_*.py` filename pattern.

## Baselines

Save a named baseline:

```sh
uv run pytest tests/benchmarks/performance --benchmark-enable --benchmark-save=baseline
```

Saved runs are written under `.benchmarks/`. That directory is ignored because
benchmark data is machine- and environment-specific.

Compare the current run against the latest saved run:

```sh
uv run pytest tests/benchmarks/performance --benchmark-enable --benchmark-compare
```

Compare against a specific saved run:

```sh
uv run pytest tests/benchmarks/performance --benchmark-enable --benchmark-compare=0001
```

Fail the run on a regression:

```sh
uv run pytest tests/benchmarks/performance --benchmark-enable --benchmark-compare --benchmark-compare-fail=mean:10%
```

## Reports

Write a JSON report:

```sh
uv run pytest tests/benchmarks/performance --benchmark-enable --benchmark-json=benchmark.json
```

Write an HTML report:

```sh
uv run pytest tests/benchmarks/performance --benchmark-enable --benchmark-html=tests/benchmarks/report.html
```

HTML reports require the optional `pytest-benchmark[html]` dependencies.

Generate histograms:

```sh
uv run pytest tests/benchmarks/performance --benchmark-enable --benchmark-histogram
```

Histogram support requires the optional `pytest-benchmark[histogram]`
dependencies.

## Calibration

By default, `pytest-benchmark` calibrates rounds and iterations automatically.
Prefer that mode for this suite. Use `benchmark.pedantic(...)` only when a
benchmark needs exact setup, teardown, rounds, or iterations; it is easy to
misconfigure for very fast functions.
