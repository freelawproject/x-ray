"""Local type annotations for PyMuPDF's public API."""

from collections.abc import Callable
from pathlib import Path
from typing import Literal, Protocol, TypedDict

import pymupdf

BBox = tuple[float, float, float, float]
Color = float | tuple[float, ...]


class _DocumentFactory(Protocol):
    def __call__(
        self,
        filename: str | Path | None = None,
        *,
        stream: bytes | None = None,
        filetype: str | None = None,
    ) -> pymupdf.Document: ...


class InsertPdf(Protocol):
    def __call__(
        self,
        docsrc: pymupdf.Document,
        *,
        from_page: int,
        to_page: int,
    ) -> None: ...


# PyMuPDF does not annotate these call signatures.
open_document: _DocumentFactory = pymupdf.Document
set_aa_level: Callable[[int], None] = pymupdf.TOOLS.set_aa_level


class TracedRect(pymupdf.Rect):
    """A rectangle with its drawing order and color attached."""

    seqno: int
    fill: Color

    def __init__(
        self, bbox: BBox | pymupdf.Rect, seqno: int, fill: Color
    ) -> None:
        initialize: Callable[[BBox | pymupdf.Rect], None] = super().__init__
        initialize(bbox)
        self.seqno = seqno
        self.fill = fill


DrawingItem = (
    tuple[Literal["re"], pymupdf.Rect, int]
    | tuple[Literal["l"], pymupdf.Point, pymupdf.Point]
    | tuple[
        Literal["c"],
        pymupdf.Point,
        pymupdf.Point,
        pymupdf.Point,
        pymupdf.Point,
    ]
    | tuple[Literal["qu"], pymupdf.Quad]
)


class Drawing(TypedDict):
    fill_opacity: float | None
    fill: Color | None
    seqno: int
    items: list[DrawingItem]


class TextSpan(TypedDict):
    seqno: int
    color: Color
    bbox: BBox
    chars: tuple[tuple[int, int, tuple[float, float], BBox], ...]
