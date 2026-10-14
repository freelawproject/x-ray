"""Types for x-ray's redaction results."""

from typing import TypedDict

from ._pymupdf import BBox, TracedRect


class RedactionType(TypedDict):
    """A type for a redaction"""

    bbox: BBox
    text: str


# The type used for the top-level dictionary of all redactions for a document
PdfRedactionsDict = dict[int, list[RedactionType]]


class CharDictType(TypedDict):
    """A type for a character dictionary"""

    rect: TracedRect
    c: str
