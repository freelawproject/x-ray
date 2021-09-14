"""Tools for working with text strings"""
import re


def is_repeated_chars(text: str) -> bool:
    """Find repeated characters in a redaction.

    This often indicates something like XXXXXXXX under the redaction or a bunch
    of space, etc.

    :param text: A string to check
    :returns: True if only repeated characters, else False
    """
    if len(text) <= 1:
        return False

    if len(set(text)) == 1:
        # There's only one unique character in the string
        return True

    return False


def is_ok_words(text: str) -> bool:
    """Check if the redaction is one of several words that are OK

    :param text: A string to check
    :returns: True if it's an OK word, else False
    """
    text = " ".join(text.strip().split())
    text = re.sub(
        r"confidential|name +redacted|privileged?|re|red|reda|redac|redact|"
        r"redacte|redacted|redacted +and +publicly +filed|",
        "",
        text,
        flags=re.IGNORECASE | re.MULTILINE,
    )
    return len(text) > 0
