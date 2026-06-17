import pytest

from xray.text_utils import is_ok_words, is_repeated_chars, looks_like_a_date


@pytest.mark.parametrize(
    ("func", "sample", "expected"),
    (
        (looks_like_a_date, "12/13/21", True),
        (looks_like_a_date, "asdf 1/1/2022", False),
        (is_repeated_chars, "XXXXXXXX", True),
        (is_repeated_chars, "redacted", False),
        (is_ok_words, "REDACTED", True),
        (is_ok_words, "The Ring travels by way of Cirith Ungol", True),
    ),
)
def benchmark_text_predicates(benchmark, func, sample, expected):
    result = benchmark(func, sample)

    assert result is expected
