import xray
from xray.pdf_utils import get_bad_redactions, get_good_rectangles


def test_bad_redaction_fixture_contents(
    bad_redaction_page, bad_redaction_path, expected_redaction_text
):
    rectangles = get_good_rectangles(bad_redaction_page)
    redactions = get_bad_redactions(bad_redaction_page)
    inspected = xray.inspect(bad_redaction_path)

    assert len(rectangles) == 3
    assert [redaction["text"] for redaction in redactions] == (
        expected_redaction_text
    )
    assert [redaction["text"] for redaction in inspected[1]] == (
        expected_redaction_text
    )


def test_bad_redaction_bytes_fixture_contents(
    bad_redaction_bytes, expected_redaction_text
):
    inspected = xray.inspect(bad_redaction_bytes)

    assert [redaction["text"] for redaction in inspected[1]] == (
        expected_redaction_text
    )


def test_tricky_clean_fixture_has_rectangles_but_no_bad_redactions(
    tricky_clean_page,
):
    rectangles = get_good_rectangles(tricky_clean_page)
    redactions = get_bad_redactions(tricky_clean_page)

    assert len(rectangles) == 3
    assert redactions == []
