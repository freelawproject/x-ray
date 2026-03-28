"""Tools for working with text strings"""

import re

from xray.custom_types import PdfRedactionsDict, RedactionType


def is_repeated_chars(text: str) -> bool:
    """Find repeated characters in a redaction.

    This often indicates something like XXXXXXXX under the redaction or a bunch
    of space, etc.

    :param text: A string to check
    :returns: True if only repeated characters, else False
    """
    if len(text) <= 1:
        return False

    # Return True if there's only one unique character in the string
    return len(set(text)) == 1


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
        r"confidential|name +redacted|privileged?|re|red|reda|redac|redact|"
        r"redacte|redacted|redacted +and +publicly +filed|"
        # Court form boilerplate: blank lines with "District of" between
        # them (e.g., "__________ District of __________").  These are
        # fill-in-the-blank fields on standard court cover sheets, not
        # redacted content.
        r"_+\s*district\s+of\s*_+|",
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

    :param text: The text found under the redaction
    :returns True if it's a date, else False
    """
    text = re.sub(r"[0-3]?\d[/\-][0-3]?\d[/\-]\d{2,4}", "", text)
    return len(text) == 0
