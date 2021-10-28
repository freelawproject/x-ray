"""
Utilities for working with PDFs and redactions
"""
import re
import typing
from typing import List, Tuple

import fitz
from fitz import Page, Rect

from .custom_types import CharDictType, RedactionType
from .text_utils import is_ok_words, is_repeated_chars


def get_good_rectangles(page: Page) -> List[Rect]:
    """Find rectangles in the PDFs that might be redactions.

    :param page: The PyMuPDF Page to look for rectangles within.
    :returns A list of PyMUPDF.Rect objects for each non-white, fully opaque
    rectangle that's big enough to be a possible redaction. If none, returns
    an empty list. Also enhances the Rect object by including the sequence
    number and fill color of the parent drawing. This allows us to later
    determine if a letter is above or below a rectangle or whether it's the
    same color.
    """
    drawings = page.get_drawings()
    good_rectangles = []
    for drawing in drawings:
        if drawing.get("fill_opacity") is None or drawing["fill_opacity"] != 1:
            # Not opaque. Probably a highlight or similar.
            continue

        if drawing["fill"] in (
            # Unfilled box (transparent to the eye, but distinct from ones that
            # have opacity of 0).
            None,
            # White
            (1.0, 1.0, 1.0),
        ):
            # White or unfilled box. These are used for various purposes
            # like, with line number columns, borders, etc. Ignore them.
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
            # Give it the sequence number and color of its parent drawing
            rectangle.seqno = drawing["seqno"]
            rectangle.color = drawing["fill"]
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
    text_rect: Rect,
    rectangles: List[Rect],
    occlusion_threshold: float = 0.0,
) -> bool:
    """Determine if a rectangle intersects is occluded by a list of others

    This uses Rect objects, but note that they must have extra attributes of
    "color" and "seqno".

    :param text_rect: The rectangle around the text to check for intersections.
    :param rectangles: A list of rectangles to check for intersections.
    :param occlusion_threshold: How much the rectangle must be occluded by at
    least one of the rectangles for it to be considered an intersection, as a
    percentage. E.g., 1.0 means that the bbox must be fully occluded, 0.10
    means it must be 10% occluded. The default, 0.0, means they must intersect
    at least a little.
    :return True if any part of the bbox intersects with any of the rectangles,
    else False.
    """
    for rect in rectangles + [text_rect]:
        assert all(
            [hasattr(rect, "seqno"), hasattr(rect, "color")]
        ), "Rectangle lacks required 'seqno' or 'color' attribute."

    overlapping_areas = []
    for rect in rectangles:
        intersecting_area = abs(text_rect & rect)
        if intersecting_area > 0 and rect.seqno > text_rect.seqno:
            # Intersecting and text was drawn first,
            # meaning it's behind the drawing.
            overlapping_areas.append(intersecting_area)
            continue
        if intersecting_area > 0 and rect.color == text_rect.color:
            # Intersecting and same color. This makes text invisible.
            overlapping_areas.append(intersecting_area)
            continue

    if not overlapping_areas:
        return False

    greatest_occluded = max(overlapping_areas)
    area_of_bbox = abs(text_rect.get_area())

    percent_occluded = greatest_occluded / area_of_bbox
    if percent_occluded > occlusion_threshold:
        return True
    return False


def get_intersecting_chars(
    page: Page, rectangles: List[Rect]
) -> List[CharDictType]:
    """Get the chars that are occluded by the rectangles

    We do this in two stages. First, we check for intersecting spans, then we
    check for intersecting chars within those spans. The idea of this is

    :param page: The PyMuPDF.Page object to inspect
    :param rectangles: A list of PyMuPDF.Rect objects from the page (aka the
    redactions).
    :return A list of characters that are under the rectangles
    """
    if len(rectangles) == 0:
        return []

    spans = page.get_texttrace()
    intersecting_chars = []
    for span in spans:
        span_seq_no = span["seqno"]
        span_color = span["color"]
        span_rect = fitz.Rect(span["bbox"])
        span_rect.seqno = span_seq_no
        span_rect.color = span_color
        if not intersects(span_rect, rectangles):
            continue
        for char in span["chars"]:
            char_rect = fitz.Rect(char[3])
            char_rect.seqno = span_seq_no
            char_rect.color = span_color
            if intersects(char_rect, rectangles, occlusion_threshold=0.8):
                char_dict: CharDictType = {
                    "rect": char_rect,
                    "c": chr(char[0]),
                }
                intersecting_chars.append(char_dict)

    return intersecting_chars


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
            if char["rect"] & rect:
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
