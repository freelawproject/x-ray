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
            1,  # White background in grayscale
            (1.0,),  # Also grayscale
            (1.0, 1.0, 1.0),  # White in RGB
            (0.0, 0.0, 0.0, 0.0),  # White in CMYK
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
    overlapping_areas = []
    for rect in rectangles:
        intersecting_area = abs(text_rect & rect)
        if intersecting_area > 0 and rect.seqno > text_rect.seqno:
            # Intersecting and text was drawn first,
            # meaning it's behind the drawing.
            overlapping_areas.append(intersecting_area)
            continue
        if intersecting_area > 0 and rect.color == text_rect.color:
            # Intersecting and same color. This makes text invisible. Note that
            # colors in PyMuPDF can be in one of several colorspaces. If that's
            # the case, you could compare something like 0.0 (grayscale) to
            # (0, 0, 0) (RGB), and say they're different, when in fact they're
            # the same. This would miss a bad redaction.
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


def make_rect_for_char(
    origin: Tuple[float, float],
    width: float,
    font_size: float,
    ascender: float,
    descender: float,
    color: float,
    seqno: int,
) -> Rect:
    """Compute character bbox.

    :param origin: An x-y pair of the location of the origin of the char
    :param width: The width of the char
    :param font_size: The size of the font
    :param ascender: The height of the ascender
    :param descender: The depth of the descender
    :param color: The color of the text
    :param seqno: The sequence number of the text
    :returns a PyMuPDF.Rect object representing the bbox around the char.
    """
    x0 = origin[0]
    x1 = x0 + width
    y0 = origin[1] - ascender * font_size
    y1 = origin[1] - descender * font_size
    rect = fitz.Rect(x0, y0, x1, y1)
    rect.color = color
    rect.seqno = seqno
    return rect


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

    spans = page._get_texttrace()
    intersecting_chars = []
    for span in spans:
        span_seq_no = span["seqno"]
        span_color = span["color"]
        for char in span["chars"]:
            origin = char[2]
            char_rect = make_rect_for_char(
                origin=origin,
                width=char[3],
                font_size=span["size"],
                ascender=span["ascender"],
                descender=span["descender"],
                color=span_color,
                seqno=span_seq_no,
            )
            if intersects(char_rect, rectangles, occlusion_threshold=0.8):
                char_dict: CharDictType = {
                    "origin": origin,
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
