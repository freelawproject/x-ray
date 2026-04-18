"""Custom types for MyPy"""

from enum import Enum
from typing import TypedDict

from fitz import Rect


class BadRedactionType(str, Enum):
    """The type of bad redaction detected.

    Using ``str, Enum`` so values serialize to JSON naturally
    without a custom encoder.
    """

    TEXT_UNDER_RECTANGLE = "TEXT_UNDER_RECTANGLE"
    UNAPPLIED_REDACT_ANNOTATION = "UNAPPLIED_REDACT_ANNOTATION"
    DARK_HIGHLIGHT_ANNOTATION = "DARK_HIGHLIGHT_ANNOTATION"
    CROSS_HATCHED_PATTERN = "CROSS_HATCHED_PATTERN"
    TEXT_UNDER_IMAGE = "TEXT_UNDER_IMAGE"
    PII_UNDER_RECTANGLE = "PII_UNDER_RECTANGLE"
    TOC_BOOKMARK_LEAK = "TOC_BOOKMARK_LEAK"


class RedactionType(TypedDict):
    """A type for a redaction"""

    bbox: tuple[float, ...]
    text: str
    type: BadRedactionType


# The type used for the top-level dictionary of all redactions for a document
PdfRedactionsDict = dict[int, list[RedactionType]]


class CharDictType(TypedDict):
    """A type for a character dictionary"""

    rect: Rect
    c: str
