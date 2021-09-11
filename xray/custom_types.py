"""Custom types for MyPy"""

from typing import Tuple, TypedDict


class RedactionType(TypedDict):
    """A type for a redaction"""

    bbox: Tuple[float, ...]
    text: str


class CharDictType(TypedDict):
    """A type for a character dictionary"""

    origin: Tuple[float, float]
    bbox: Tuple[float, float, float, float]
    c: str
