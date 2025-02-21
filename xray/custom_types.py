"""Custom types for MyPy"""

from typing import TypedDict

from fitz import Rect


class RedactionType(TypedDict):
    """A type for a redaction"""

    bbox: tuple[float, ...]
    text: str


# The type used for the top-level dictionary of all redactions for a document
PdfRedactionsDict = dict[int, list[RedactionType]]


class CharDictType(TypedDict):
    """A type for a character dictionary"""

    rect: Rect
    c: str
