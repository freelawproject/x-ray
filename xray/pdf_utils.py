"""
Utilities for working with PDFs and redactions
"""

from itertools import chain
from typing import List, Tuple

import fitz
from fitz import Page, Rect

from .custom_types import CharDictType, RedactionType


def get_good_rectangles(page: Page) -> List[Rect]:
    """Find rectangles in the PDFs that might be redactions.

    :param page: The PyMuPDF Page to look for rectangles within.
    :returns A list of PyMUPDF.Rect objects for each black rectangle that's
    big enough to be a possible redaction. If none, returns an empty list.
    """
    drawings = page.get_drawings()
    good_rectangles = []
    for drawing in drawings:
        if drawing.get("rect") is None:
            # Not a rectangle (ok, ok, tetrahedron, technically)
            continue
        if drawing["fill"] != (0.0,):
            # Not black
            continue

        rectangle = drawing["rect"]

        if rectangle.y1 <= 43:
            # It's a header, ignore it
            continue

        if all(
            [
                # Eliminate horizontal lines
                rectangle.height > 4,
                # Eliminate vertical bars? Unsure what this is supposed to
                # prevent?
                rectangle.width > 4,
            ]
        ):
            good_rectangles.append(rectangle)
    return good_rectangles


def intersects(bbox: Tuple[float, ...], rectangles: List[Rect]) -> bool:
    """Determine if a bbox intersects with any of a list of rectangles

    :param bbox: A four-tuple of floats denoting a bounding box of a rectangle.
    The first two floats represent the upper left corner, and the second two
    are the bottom right. Note that the Y-axis is reversed so it starts at the
    top of the page, not the bottom left.
    :param rectangles: A list of PyMuPDF.Rect objects
    :return True if any part of the bbox intersects with any of the rectangles,
    else False.
    """
    for rect in rectangles:
        if Rect(*bbox) & rect:
            return True
    return False


def get_intersecting_chars(
    page: Page, rectangles: List[Rect]
) -> List[CharDictType]:
    """Get the chars that are occluded by the rectangles

    PDF pages in PyMuPDF are broken up into blocks of text, those blocks
    contain lines, the lines contain spans, and the spans contain characters.
    Due to all this, what we do here is start with the biggest object, then
    drill down and filter iteratively until we have just the chars we want.

    We start with the block objects and check if any of them intersect with the
    rectangles. If so, we continue with those. Then we do the same for lines,
    then spans, then characters. The idea here is that we avoid looking for
    intersections in every danged character, by eliminating blocks that don't
    intersect, then lines that don't, then spans that don't, then chars that
    don't.

    Along the way, we do a couple extra filters, like looking for black text,
    etc.

    :param page: The PyMuPDF.Page object to inspect
    :param rectangles: A list of PyMuPDF.Rect objects from the page (aka the
    redactions).
    :return A list of characters that are under the rectangles
    """
    if len(rectangles) == 0:
        return []

    blocks = page.get_text(
        "rawdict",
        flags=fitz.TEXT_PRESERVE_LIGATURES
        | fitz.TEXT_PRESERVE_WHITESPACE
        | fitz.TEXT_DEHYPHENATE,
    )["blocks"]

    # Filter blocks with lines that intersect
    good_blocks = filter(lambda block: "lines" in block, blocks)
    intersecting_blocks = filter(
        lambda block: intersects(block["bbox"], rectangles),
        good_blocks,
    )

    # Filter to intersecting lines
    lines = chain(*[block["lines"] for block in intersecting_blocks])
    intersecting_lines = filter(
        lambda line: intersects(line["bbox"], rectangles),
        lines,
    )

    # Filter to intersecting spans that are black
    spans = chain(*[line["spans"] for line in intersecting_lines])
    good_spans = filter(lambda span: span["color"] == 0, spans)
    intersecting_spans = filter(
        lambda span: intersects(span["bbox"], rectangles),
        good_spans,
    )

    # Get a flat list of intersecting chars
    chars = chain(*[span["chars"] for span in intersecting_spans])
    intersecting_chars = filter(
        lambda char: intersects(char["bbox"], rectangles),
        chars,
    )
    return list(intersecting_chars)


def group_chars_by_rect(
    chars: List[CharDictType],
    rectangles: List[Rect],
) -> List[RedactionType]:
    """Take the chars that intersected with rectangles, and the rectangles they
    intersected with and group the chars back into words along with the bboxes
    of the rectangles they intersected with.

    :param chars: The list of character dicts that intersect with rectangles in
    the PDF.
    :param rectangles: A list of PyMuPDF.Rect objects from the page (aka the
    redactions).
    :return: A list of dictionaries with keys for the rectangle's BBOX and the
    words underneath it.
    """
    redactions = []
    for rect in rectangles:
        redaction: RedactionType = {
            "bbox": (rect.x0, rect.y0, rect.x1, rect.y1),
            "text": "",
        }
        for char in chars:
            if Rect(*char["bbox"]) & rect:
                redaction["text"] += char["c"]
        redactions.append(redaction)
    return redactions


def get_bad_redactions(page: Page) -> List[RedactionType]:
    """Get the bad redactions for a page from a PDF

    :param: page: The PyMuPDF.Page from a PDF
    :returns: A list of char objects that are under the rectangles. Each is a
    dict that has an origin, bbox, and a character.
    """
    good_rectangles = get_good_rectangles(page)
    intersecting_chars = get_intersecting_chars(page, good_rectangles)
    bad_redactions = group_chars_by_rect(intersecting_chars, good_rectangles)
    return bad_redactions
