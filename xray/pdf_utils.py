"""
Utilities for working with PDFs and redactions
"""

import re
from collections.abc import Callable

import pymupdf as fitz
from pymupdf import Document, Page, Rect

from ._pymupdf import (
    BBox,
    Drawing,
    InsertPdf,
    TextSpan,
    TracedRect,
    open_document,
    set_aa_level,
)
from .custom_types import CharDictType, RedactionType
from .text_utils import is_ok_words, is_repeated_chars

# Disable anti-aliasing when rendering and creating pixmaps
set_aa_level(0)


def get_good_rectangles(page: Page) -> list[TracedRect]:
    """Find rectangles in the PDFs that might be redactions.

    :param page: The PyMuPDF Page to look for rectangles within.
    :returns A list of PyMUPDF.Rect objects for each non-white, fully opaque
    rectangle that's big enough to be a possible redaction. If none, returns
    an empty list. Also enhances the Rect object by including the sequence
    number and fill color of the parent drawing. This allows us to later
    determine if a letter is above or below a rectangle or whether it's the
    same color.
    """
    drawings: list[Drawing] = page.get_drawings()
    good_rectangles = []
    for drawing in drawings:
        if drawing.get("fill_opacity") is None or drawing["fill_opacity"] != 1:
            # Not opaque. Probably a highlight or similar.
            continue

        if drawing["fill"] is None:
            # Unfilled box (transparent to the eye, but distinct from ones that
            # have opacity of 0).
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
        rectangles = [
            TracedRect(item[1], drawing["seqno"], drawing["fill"])
            for item in drawing["items"]
            if item[0] == "re"
        ]

        for rectangle in rectangles:
            if rectangle.y1 <= 43:
                # It's a header, ignore it
                continue

            height: float = rectangle.height
            width: float = rectangle.width
            if all(
                [
                    # Eliminate horizontal lines
                    height > 4,
                    # Eliminate vertical lines, like those along margins.
                    width > 4,
                ]
            ):
                is_infinite: bool = rectangle.is_infinite
                if is_infinite:
                    normalize: Callable[[], Rect] = rectangle.normalize
                    normalize()
                good_rectangles.append(rectangle)
    return good_rectangles


def intersects(
    text_rect: TracedRect,
    rectangles: list[TracedRect],
    occlusion_threshold: float = 0.0,
) -> bool:
    """Determine if a rectangle intersects is occluded by a list of others

    This uses Rect objects, but note that they must have extra attributes of
    "fill" and "seqno".

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
        assert all([hasattr(rect, "seqno"), hasattr(rect, "fill")]), (
            "Rectangle lacks required 'seqno' or 'fill' attribute."
        )

    overlapping_areas = []
    for rect in rectangles:
        intersection: Rect = text_rect & rect
        intersecting_area: float = abs(intersection)
        if intersecting_area > 0 and rect.seqno > text_rect.seqno:
            # Intersecting text was drawn first, meaning it's behind the rect.
            overlapping_areas.append(intersecting_area)
            continue
        if intersecting_area > 0 and rect.fill == text_rect.fill:
            # Intersecting and same color. This makes text invisible even if
            # it's drawn on top of the rect.
            overlapping_areas.append(intersecting_area)
            continue

    if not overlapping_areas:
        return False

    greatest_occluded = max(overlapping_areas)
    area_of_bbox = abs(text_rect.get_area())

    percent_occluded = greatest_occluded / area_of_bbox
    return percent_occluded > occlusion_threshold


def get_intersecting_chars(
    page: Page, rectangles: list[TracedRect]
) -> list[CharDictType]:
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

    get_texttrace: Callable[[], list[TextSpan]] = page.get_texttrace
    spans = get_texttrace()
    intersecting_chars = []
    for span in spans:
        span_seq_no = span["seqno"]
        span_color = span["color"]
        span_rect = TracedRect(span["bbox"], span_seq_no, span_color)
        if not intersects(span_rect, rectangles):
            continue
        for char in span["chars"]:
            char_rect = TracedRect(char[3], span_seq_no, span_color)
            if intersects(char_rect, rectangles, occlusion_threshold=0.8):
                char_dict: CharDictType = {
                    "rect": char_rect,
                    "c": chr(char[0]),
                }
                intersecting_chars.append(char_dict)

    return intersecting_chars


def group_chars_by_rect(
    chars: list[CharDictType],
    rectangles: list[TracedRect],
) -> list[RedactionType]:
    """Take the chars that intersected with rectangles, and the rectangles they
    intersected with and group the chars back into words along with the bboxes
    of the rectangles they intersected with.

    If a char intersects with more than one rectangle, only include it as part
    of the rectangle with the highest sequence number.

    :param chars: The list of character dicts that intersect with rectangles in
    the PDF.
    :param rectangles: A list of PyMuPDF.Rect objects from the page (aka the
    redactions).
    :return: A list of dictionaries with keys for the rectangle's BBOX and the
    words underneath it.
    """
    # A problem that we must deal with is stacked rectangles. Imagine a stack
    # of stuff like so:
    #
    #   On top: Some red characters, "ABC"
    #   Then: A white rect
    #   On bottom: A red rect
    #
    # In this case, you can see the letters because they have a white
    # background. It's not a bad redaction, even though the letters intersect
    # with each of the rectangles. These need to get coalesced into a single
    # bad redaction.
    #
    # Reverse-sort the rectangles by sequence number, and eliminate each char
    # as soon as it intersects a rectangle.
    redactions = []

    # Sort the rectangles by reversed sequence key.
    def sequence_number(rect: TracedRect) -> int:
        return rect.seqno

    seq_sorted_rects = sorted(rectangles, key=sequence_number, reverse=True)
    for rect in seq_sorted_rects:
        redaction: RedactionType = {
            "bbox": (rect.x0, rect.y0, rect.x1, rect.y1),
            "text": "",
        }
        # Make a copy of the chars list so we can manipulate it in the loop
        char_copy = chars.copy()
        for char in char_copy:
            intersection: Rect = char["rect"] & rect
            area: float = abs(intersection)
            if area:
                # The char intersects with this rectangle. Add it to the
                # redaction dict, and remove it from the list so it doesn't
                # get analyzed again.
                redaction["text"] += char["c"]
                chars.remove(char)
        redactions.append(redaction)

    return redactions


def filter_redactions_by_text(
    redactions: list[RedactionType],
) -> list[RedactionType]:
    """Filter out redactions that are not actually bad.

    :param redactions: A list of redactions that might be bad
    :return: A (hopefully) smaller list of redactions
    """
    return [
        redaction
        for redaction in redactions
        # Exclude repeated characters such as XXXX.
        if not is_repeated_chars(redaction["text"])
        # Require non-whitespace content.
        and redaction["text"].strip()
        # Require letters or numbers beneath the rectangle.
        and re.search(r"[\d\w]", redaction["text"])
        # Exclude acceptable redaction labels such as "confidential".
        and is_ok_words(redaction["text"])
    ]


def filter_redactions_by_pixmap(
    redactions: list[RedactionType],
    page: Page,
) -> list[RedactionType]:
    """Keep rectangles whose solid fill reproduces the page's appearance.

    Render a temporary page before and after painting the rectangle. Exact
    pixel equality confirms that it already appears as a solid rectangle.
    Comparing the full page also preserves pixels at fractional boundaries.

    :param redactions: A list of redactions that might be bad
    :param page: The PyMuPDF.Page object where the bad redactions might be
    :return: The redactions, if they are valid
    """
    if not redactions:
        return []

    source: Document | None = page.parent
    page_number: int | None = page.number
    if source is None or page_number is None:
        raise ValueError("orphaned object: parent is None")

    bad_redactions = []
    for redaction in redactions:
        copy = open_document()
        with copy:
            insert_pdf: InsertPdf = copy.insert_pdf
            insert_pdf(source, from_page=page_number, to_page=page_number)
            # Include annotations in the page content before painting over it.
            bake: Callable[[], None] = copy.bake
            bake()
            copied_page = copy[0]
            set_rotation: Callable[[int], None] = copied_page.set_rotation
            set_rotation(0)
            page_rect: Rect = copied_page.rect
            intersects_page: Callable[[BBox], bool] = page_rect.intersects
            if not intersects_page(redaction["bbox"]):
                continue

            before = copied_page.get_pixmap(colorspace=fitz.csRGB)
            width: int = before.width
            height: int = before.height
            origin_x: int = before.x
            origin_y: int = before.y
            x0, y0, x1, y1 = redaction["bbox"]
            x = min(max(int((x0 + x1) / 2) - origin_x, 0), width - 1)
            y = min(max(int((y0 + y1) / 2) - origin_y, 0), height - 1)
            pixel: Callable[[int, int], tuple[int, int, int]] = before.pixel
            color = tuple(channel / 255 for channel in pixel(x, y))
            copied_page.draw_rect(redaction["bbox"], color=None, fill=color)

            after = copied_page.get_pixmap(colorspace=fitz.csRGB)
            before_pixels: bytes = before.samples
            after_pixels: bytes = after.samples
            if before_pixels == after_pixels:
                bad_redactions.append(redaction)
    return bad_redactions


def get_bad_redactions(page: Page) -> list[RedactionType]:
    """Get the bad redactions for a page from a PDF

    :param: page: The PyMuPDF.Page from a PDF
    :returns: A list of char objects that are under the rectangles. Each is a
    dict that has an origin, bbox, and a character.
    """
    good_rectangles = get_good_rectangles(page)
    intersecting_chars = get_intersecting_chars(page, good_rectangles)
    redactions = group_chars_by_rect(intersecting_chars, good_rectangles)
    bad_redactions = filter_redactions_by_text(redactions)
    bad_redactions = filter_redactions_by_pixmap(bad_redactions, page)
    return bad_redactions
