"""Custom types for MyPy"""

from typing import Dict, List, Tuple, TypedDict


class RedactionType(TypedDict):
    """A type for a redaction"""

    bbox: Tuple[float, ...]
    text: str


# The type used for the top-level dictionary of all redactions for a document
PdfRedactionsDict = Dict[int, List[RedactionType]]


class CharDictType(TypedDict):
    """A type for a character dictionary"""

    origin: Tuple[float, float]
    bbox: Tuple[float, float, float, float]
    c: str
