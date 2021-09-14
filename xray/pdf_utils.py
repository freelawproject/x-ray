"""
Utilities for working with PDFs and redactions
"""
import re
import typing
from itertools import chain
from typing import List, Tuple

import fitz
from fitz import Page, Rect

from .custom_types import CharDictType, RedactionType
from .text_utils import is_ok_words, is_repeated_chars


def get_good_rectangles(page: Page) -> List[Rect]:
    """Find rectangles in the PDFs that might be redactions.

    :param page: The PyMuPDF Page to look for rectangles within.
    :returns A list of PyMUPDF.Rect objects for each black rectangle that's
    big enough to be a possible redaction. If none, returns an empty list.
    """
    drawings = page.get_drawings()
    good_rectangles = []
    for drawing in drawings:
        if drawing.get("fill_opacity") is None or drawing["fill_opacity"] != 1:
            # Not opaque. Probably a highlight or similar.
            continue

        if drawing["fill"] in (
            1,  # Grayscale
            (1.0,),  # Also grayscale
            (1.0, 1.0, 1.0),  # RGB
            (0.0, 0.0, 0.0, 0.0),  # CMYK
        ):
            # White box. These are used for various purposes like, with line
            # number columns. Ignore them.
            continue

        # Each drawing can contain multiple "draw" commands that could be
        # rectangles, lines, quads or curves. Each takes the form of a tuple,
        # where the first item is the type for the object, then the rest of the
        # items in the tuple define the object. In the case of rectangles, the
        # type is "re", and the second key is a fitz.Rect object. Gather those
        # here.
        #
        # N.B.: Each _drawing_ also contains a key for "rect" that defines a
        # rectangle around the whole shape. Using that, however, you will get
        # the outer dimensions of multi-line redactions, which will make you
        # sad. For example:
        #
        # +----------------------------------------------------+
        # | some visible letters █████████████████████████████ |
        # | ████████████████████████████████ more letters here |
        # +----------------------------------------------------+
        #
        # If you use the dimensions of the outer rectangle, you will wrongly
        # say that the letters before and after the redaction are badly
        # redacted. Instead, use the rectangles from the "items" key, which in
        # the above example would yield two rectangles ("re" types).
        rectangles = [item[1] for item in drawing["items"] if item[0] == "re"]

        for rectangle in rectangles:
            if rectangle.y1 <= 43:
                # It's a header, ignore it
                continue

            if all(
                [
                    # Eliminate horizontal lines
                    rectangle.height > 4,
                    # Eliminate vertical lines, like those along margins.
                    rectangle.width > 4,
                ]
            ):
                if rectangle.is_infinite:
                    rectangle.normalize()
                good_rectangles.append(rectangle)
    return good_rectangles


def intersects(
    bbox: Tuple[float, ...],
    rectangles: List[Rect],
    occlusion_threshold: float = 0.0,
) -> bool:
    """Determine if a bbox intersects with any of a list of rectangles

    :param bbox: A four-tuple of floats denoting a bounding box of a rectangle.
    The first two floats represent the upper left corner, and the second two
    are the bottom right. Note that the Y-axis is reversed so it starts at the
    top of the page, not the bottom left.
    :param rectangles: A list of PyMuPDF.Rect objects
    :param occlusion_threshold: How much the bbox must be occluded by at least
    one of the rectangles for it to be considered an intersection, as a
    percentage. E.g., 1.0 means that the bbox must be fully occluded, 0.10
    means it must be 10% occluded. The default, 0.0, means they must intersect
    at least a little.
    :return True if any part of the bbox intersects with any of the rectangles,
    else False.
    """
    overlapping_areas = []
    for rect in rectangles:
        # The overlapping area of two rectangles is defined by the product of
        # the length of their vertical and horizontal intersections.
        # See: https://stackoverflow.com/a/52194761/64911, in particular the
        # image that shows the bolded horizontal and vertical lines that get
        # multiplied.
        #
        # As a formula, this takes the form of:
        #
        #   A = max(0, min(r0, r1) - max(l0, l1)) *   # horizontal intersection
        #         max(0, min(b0, b1) - max(t0, t1))   # vertical intersection
        bbox_left, bbox_top, bbox_right, bbox_bottom = (
            bbox[0],
            bbox[1],
            bbox[2],
            bbox[3],
        )
        rect_left, rect_top, rect_right, rect_bottom = (
            rect.x0,
            rect.y0,
            rect.x1,
            rect.y1,
        )
        vertical_intersection = max(
            0.0, min(bbox_bottom, rect_bottom) - max(bbox_top, rect_top)
        )
        horizontal_intersection = max(
            0.0, min(bbox_right, rect_right) - max(bbox_left, rect_left)
        )
        overlapping_area = horizontal_intersection * vertical_intersection
        overlapping_areas.append(overlapping_area)

    greatest_occluded = max(overlapping_areas)
    area_of_bbox = Rect(*bbox).get_area()

    percent_occluded = greatest_occluded / area_of_bbox
    if percent_occluded > occlusion_threshold:
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
        lambda char: intersects(
            char["bbox"], rectangles, occlusion_threshold=0.8
        ),
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


@typing.no_type_check  # It gets confused w/filters
def filter_redactions(redactions: List[RedactionType]) -> List[RedactionType]:
    """Filter out redactions that are not actually bad.

    :param redactions: A list of redactions that might be bad
    :return: A (hopefully) smaller list of redactions
    """
    # Isn't just repeated text like XXXX
    redactions = filter(lambda r: not is_repeated_chars(r["text"]), redactions)

    # Has non-whitespace content and isn't blank
    redactions = filter(lambda r: r["text"].strip(), redactions)

    # Has some letters or numbers
    redactions = filter(lambda r: re.search(r"[\d\w]", r["text"]), redactions)

    # Has OK words in redaction
    redactions = filter(lambda r: is_ok_words(r["text"]), redactions)

    return list(redactions)


def get_bad_redactions(page: Page) -> List[RedactionType]:
    """Get the bad redactions for a page from a PDF

    :param: page: The PyMuPDF.Page from a PDF
    :returns: A list of char objects that are under the rectangles. Each is a
    dict that has an origin, bbox, and a character.
    """
    good_rectangles = get_good_rectangles(page)
    intersecting_chars = get_intersecting_chars(page, good_rectangles)
    redactions = group_chars_by_rect(intersecting_chars, good_rectangles)
    bad_redactions = filter_redactions(redactions)
    return bad_redactions
