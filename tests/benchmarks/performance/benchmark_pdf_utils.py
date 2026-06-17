import xray
from xray.pdf_utils import get_bad_redactions, get_good_rectangles


def benchmark_get_good_rectangles(benchmark, bad_redaction_page):
    rectangles = benchmark(get_good_rectangles, bad_redaction_page)

    assert len(rectangles) == 3


def benchmark_get_bad_redactions(
    benchmark, bad_redaction_page, expected_redaction_text
):
    redactions = benchmark(get_bad_redactions, bad_redaction_page)

    assert [redaction["text"] for redaction in redactions] == (
        expected_redaction_text
    )


def benchmark_get_bad_redactions_clean_doc(benchmark, tricky_clean_page):
    redactions = benchmark(get_bad_redactions, tricky_clean_page)

    assert redactions == []


def benchmark_inspect_path(
    benchmark, bad_redaction_path, expected_redaction_text
):
    redactions = benchmark(xray.inspect, bad_redaction_path)

    assert [redaction["text"] for redaction in redactions[1]] == (
        expected_redaction_text
    )


def benchmark_inspect_bytes(
    benchmark, bad_redaction_bytes, expected_redaction_text
):
    redactions = benchmark(xray.inspect, bad_redaction_bytes)

    assert [redaction["text"] for redaction in redactions[1]] == (
        expected_redaction_text
    )
