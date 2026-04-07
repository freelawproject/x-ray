"""Tools for working with text strings"""

import re

from xray.custom_types import PdfRedactionsDict, RedactionType


def is_repeated_chars(text: str) -> bool:
    """Find repeated characters in a redaction.

    This often indicates something like XXXXXXXX under the redaction or a bunch
    of space, etc.  Also catches cases like "XXXXX XXXX" or "XXXXXXXXX]"
    where a single character is repeated with incidental whitespace or
    punctuation mixed in — these are redaction placeholders, not real
    content.

    :param text: A string to check
    :returns: True if only repeated characters, else False
    """
    if len(text) <= 1:
        return False

    # Return True if there's only one unique character in the string
    if len(set(text)) == 1:
        return True

    # Strip whitespace and punctuation, then check if only one unique
    # alphanumeric character remains (e.g., "XXXXX XXXX" → "XXXXXXXXX").
    alphanumeric = re.sub(r"[^a-zA-Z0-9]", "", text)
    return len(alphanumeric) > 1 and len(set(alphanumeric)) == 1


def is_single_char(text: str) -> bool:
    """Check if text contains only a single alphanumeric character.

    A single letter or digit — possibly surrounded by whitespace or
    punctuation — is not meaningful redacted content.  These commonly
    appear when a rectangle slightly overlaps an adjacent character
    (e.g., a page number or list marker).

    :param text: A string to check
    :returns: True if there is at most one alphanumeric character
    """
    return len(re.findall(r"[\w\d]", text)) <= 1


def is_ok_words(text: str) -> bool:
    """Check if the redaction is one of several words that are OK

    :param text: A string to check
    :returns: True if it's an OK word, else False
    """
    text = " ".join(text.strip().split())
    text = re.sub(
        # Longest patterns first — regex alternation is left-to-right, so
        # "re" must not consume the start of "redacted" before the longer
        # pattern gets a chance to match.
        r"redacted +and +publicly +filed|name +redacted|"
        r"confidential|privileged?|"
        r"redacted|redacte|redact|redac|reda|red|re|"
        # Court form boilerplate: blank lines with "District of" between
        # them (e.g., "__________ District of __________").  These are
        # fill-in-the-blank fields on standard court cover sheets, not
        # redacted content.
        r"_+\s*district\s+of\s*_+|"
        # Email security banners that get hidden behind yellow
        # highlight rectangles in court filings.  The banner text
        # often spans multiple rectangles, so we match both the full
        # banner and its common tail fragment.
        r"caution\s*-?\s*external\s+e-?mail[^|]*|"
        r"(exercise\s+caution\s+when\s+opening\s+)?"
        r"attachments\s+or\s+clicking\s+on\s+links\.?|",
        "",
        text,
        flags=re.IGNORECASE | re.MULTILINE,
    )
    return len(text) > 0


def check_if_all_dates(redactions: PdfRedactionsDict) -> PdfRedactionsDict:
    """Check if every redaction in a doc is a date

    :param redactions: The PDF redaction dict for an entire document
    :returns: The redaction list that was passed in, or an empty list if they
    are all dates.
    """
    redaction_list: list[RedactionType]
    for redaction_list in redactions.values():
        for redaction in redaction_list:
            if not looks_like_a_date(redaction["text"]):
                return redactions

    # Everything looked like a date, therefore no bad redactions.
    return {}


def looks_like_a_date(text: str) -> bool:
    """Is the redaction, in its entirety, a date?

    Also handles truncated date fragments like "03/23/" or "03/23/201"
    that occur when a rectangle boundary clips a date.  Trailing
    date separators (/ and -) are stripped before checking.

    :param text: The text found under the redaction
    :returns True if it's a date, else False
    """
    # Strip trailing separators left by clipped dates (e.g., "03/23/")
    text = text.rstrip("/-")
    text = re.sub(r"[0-3]?\d[/\-][0-3]?\d([/\-]\d{0,4})?", "", text)
    return len(text) == 0
