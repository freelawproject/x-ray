from pathlib import Path
from typing import cast

import pytest

import xray
from tests.conftest import BENCHMARK_ASSETS

GROUND_TRUTH = {
    "rectangles_yes.pdf": {
        "category": "should_detect",
        "expected_detections": 3,
    },
    "rectangles_yes_2.pdf": {
        "category": "should_detect",
        "expected_detections": 1,
    },
    "bad_cross_hatched_redactions.pdf": {
        "category": "should_not_detect",
        "expected_detections": 0,
    },
    "hidden_text_on_visible_text.pdf": {
        "category": "expected_fail",
        "expected_detections": 0,
    },
    "multi_line_redaction_ok.pdf": {
        "category": "should_not_detect",
        "expected_detections": 0,
    },
    "no_bad_redactions.2.1.pdf": {
        "category": "edge_cases",
        "expected_detections": 0,
    },
    "no_bad_redactions.3.1.pdf": {
        "category": "edge_cases",
        "expected_detections": 0,
    },
    "no_bad_redactions.3.2.pdf": {
        "category": "edge_cases",
        "expected_detections": 0,
    },
    "no_bad_redactions.4.1.pdf": {
        "category": "edge_cases",
        "expected_detections": 0,
    },
    "no_bad_redactions.5.5.pdf": {
        "category": "edge_cases",
        "expected_detections": 0,
    },
    "no_bad_redactions.6.2.pdf": {
        "category": "edge_cases",
        "expected_detections": 0,
    },
    "no_bad_redactions.7.1.pdf": {
        "category": "edge_cases",
        "expected_detections": 0,
    },
    "no_bad_redactions.8.1.pdf": {
        "category": "edge_cases",
        "expected_detections": 0,
    },
    "ok_words.pdf": {
        "category": "should_not_detect",
        "expected_detections": 0,
    },
    "partial_intersections_ok.pdf": {
        "category": "should_not_detect",
        "expected_detections": 0,
    },
    "rect_ordering_0.8.pdf": {
        "category": "edge_cases",
        "expected_detections": 0,
    },
    "rect_ordering_1.23.pdf": {
        "category": "edge_cases",
        "expected_detections": 0,
    },
    "rect_ordering_2.1.pdf": {
        "category": "edge_cases",
        "expected_detections": 0,
    },
    "rect_ordering_3.20.pdf": {
        "category": "edge_cases",
        "expected_detections": 0,
    },
    "rect_ordering_4.1.pdf": {
        "category": "edge_cases",
        "expected_detections": 0,
    },
    "rect_ordering_5.2.pdf": {
        "category": "edge_cases",
        "expected_detections": 0,
    },
    "rect_ordering_6.19.pdf": {
        "category": "edge_cases",
        "expected_detections": 0,
    },
    "rectangles_no.pdf": {
        "category": "should_not_detect",
        "expected_detections": 0,
    },
    "unfilled_rect.pdf": {
        "category": "should_not_detect",
        "expected_detections": 0,
    },
    "whitespace_redactions.pdf": {
        "category": "should_not_detect",
        "expected_detections": 0,
    },
    "whitespace_redactions_2.pdf": {
        "category": "should_not_detect",
        "expected_detections": 0,
    },
    "whitespace_redaction_with_comma.pdf": {
        "category": "should_not_detect",
        "expected_detections": 0,
    },
}


def count_detections(result):
    """Count total detections across all pages."""
    return sum(len(redactions) for redactions in result.values())


def get_accuracy_test_cases():
    """Parametrize with (pdf, category, expected_count) tuples."""
    cases = []
    for pdf_param in BENCHMARK_ASSETS:
        pdf = cast(Path, pdf_param.values[0])
        spec = GROUND_TRUTH.get(pdf.name, {})
        category = spec.get("category", "unknown")
        expected_count = spec.get("expected_detections", 0)
        cases.append(
            pytest.param((pdf, category, expected_count), id=pdf.name)
        )
    return cases


@pytest.mark.parametrize("test_data", get_accuracy_test_cases())
def test_accuracy_benchmark(benchmark, test_data):
    pdf, category, expected_count = test_data

    result = benchmark.pedantic(xray.inspect, args=(pdf,), rounds=1)
    # This isn't a perf benchmark, it's a quality one, but we hook into
    # pytest-benchmark's lifecycle cleanly (extra_info, JSON output) without
    # the overhead of repeated measurements that performance testing needs.
    # By doing this we leverage existing patterns and adapt it to my needs
    actual_count = count_detections(result)

    benchmark.extra_info["category"] = category
    benchmark.extra_info["expected_detections"] = expected_count
    benchmark.extra_info["actual_detections"] = actual_count
    benchmark.extra_info["accuracy_match"] = actual_count == expected_count

    assert actual_count == expected_count, (
        f"Detection count mismatch for {pdf.name}: "
        f"expected {expected_count}, got {actual_count}"
    )
