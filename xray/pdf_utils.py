"""
Utilities for working with PDFs and redactions
"""

import re
import typing

import fitz
from fitz import Page, Rect

from .custom_types import CharDictType, RedactionType
from .text_utils import is_ok_words, is_repeated_chars

# Disable graphics antialiasing for exact rectangle comparisons, but retain
# normal text antialiasing to avoid expensive monochrome font hinting.
fitz.TOOLS.set_aa_level(0)
fitz.mupdf.fz_set_text_aa_level(8)


def get_good_rectangles(page: Page) -> list[Rect]:
    """Find rectangles in the PDFs that might be redactions.

    :param page: The PyMuPDF Page to look for rectangles within.
    :returns A list of PyMUPDF.Rect objects for each non-white, fully opaque
    rectangle that's big enough to be a possible redaction. If none, returns
    an empty list. Also enhances the Rect object by including the sequence
    number and fill color of the parent drawing. This allows us to later
    determine if a letter is above or below a rectangle or whether it's the
    same color.
    """
    drawings = page.get_cdrawings()
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
        # type is "re", and the second item gives its coordinates. Convert only
        # those items to Rect objects.
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
            Rect(item[1]).normalize()
            for item in drawing["items"]
            if item[0] == "re"
        ]

        for rectangle in rectangles:
            # Give it the sequence number and color of its parent drawing
            rectangle.seqno = drawing["seqno"]
            rectangle.fill = drawing["fill"]
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
    rectangles: list[Rect],
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

    for rect in rectangles:
        # Only a later rectangle or one with the same color can hide text.
        if rect.seqno <= text_rect.seqno and rect.fill != text_rect.fill:
            continue
        # Disjoint rectangles need no intersection geometry.
        if (
            text_rect.x0 >= rect.x1
            or text_rect.x1 <= rect.x0
            or text_rect.y0 >= rect.y1
            or text_rect.y1 <= rect.y0
        ):
            continue
        intersecting_area = abs(Rect(text_rect).intersect(rect))
        if intersecting_area > 0:
            percent_occluded = intersecting_area / abs(text_rect.get_area())
            if percent_occluded > occlusion_threshold:
                return True
    return False


def get_intersecting_chars(
    page: Page, rectangles: list[Rect]
) -> list[CharDictType]:
    """Get the chars that are occluded by the rectangles

    First match each span to its rectangles, then check its characters
    against only those rectangles.

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
        span_rect.fill = span_color
        # A span encloses its characters, so reuse its matching rectangles.
        span_rectangles = [
            rect for rect in rectangles if intersects(span_rect, [rect])
        ]
        if not span_rectangles:
            continue
        for char in span["chars"]:
            char_rect = fitz.Rect(char[3])
            char_rect.seqno = span_seq_no
            char_rect.fill = span_color
            if intersects(char_rect, span_rectangles, occlusion_threshold=0.8):
                char_dict: CharDictType = {
                    "rect": char_rect,
                    "c": chr(char[0]),
                }
                intersecting_chars.append(char_dict)

    return intersecting_chars


def group_chars_by_rect(
    chars: list[CharDictType],
    rectangles: list[Rect],
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
    seq_sorted_rects = sorted(rectangles, key=lambda x: x.seqno, reverse=True)
    for rect in seq_sorted_rects:
        redaction: RedactionType = {
            "bbox": (rect.x0, rect.y0, rect.x1, rect.y1),
            "text": "",
        }
        remaining_chars = []
        for char in chars:
            if abs(char["rect"] & rect):
                # Assign the character to this rectangle so lower rectangles
                # do not analyze it again.
                redaction["text"] += char["c"]
            else:
                remaining_chars.append(char)
        # Remove assigned characters without repeated list.remove() searches.
        chars[:] = remaining_chars
        redactions.append(redaction)

    return redactions


@typing.no_type_check  # It gets confused w/filters
def filter_redactions_by_text(
    redactions: list[RedactionType],
) -> list[RedactionType]:
    """Filter out redactions that are not actually bad.

    :param redactions: A list of redactions that might be bad
    :return: A (hopefully) smaller list of redactions
    """
    # Isn't just repeated text like XXXX
    redactions = filter(lambda r: not is_repeated_chars(r["text"]), redactions)

    # Has non-whitespace content and isn't blank
    redactions = filter(lambda r: r["text"].strip(), redactions)

    # Has some letters or numbers (isn't just a rectangle
    # with nothing under it)
    redactions = filter(lambda r: re.search(r"[\d\w]", r["text"]), redactions)

    # Has OK words in redaction
    redactions = filter(lambda r: is_ok_words(r["text"]), redactions)

    return list(redactions)


def filter_redactions_by_pixmap(
    redactions: list[RedactionType],
    page: Page,
) -> list[RedactionType]:
    """Keep rectangles whose solid fill matches the page's rendered pixels.

    Render the page once, then use each rectangle's rendered alpha mask to
    compare its fill with the page. Exact pixel equality preserves fractional
    boundaries without repeatedly rendering the page's text and images.

    :param redactions: A list of redactions that might be bad
    :param page: The PyMuPDF.Page object where the bad redactions might be
    :return: The redactions, if they are valid
    """
    if not redactions:
        return []

    # Match the unrotated coordinates used by the redaction boxes.
    page_rect = page.rect * page.derotation_matrix
    pixmap = page.get_pixmap(
        matrix=page.derotation_matrix, colorspace=fitz.csRGB
    )
    bad_redactions = []
    with fitz.open() as masks:
        for redaction in redactions:
            if not page_rect.intersects(redaction["bbox"]):
                continue

            x0, y0, x1, y1 = redaction["bbox"]
            x = min(max(int((x0 + x1) / 2) - pixmap.x, 0), pixmap.width - 1)
            y = min(max(int((y0 + y1) / 2) - pixmap.y, 0), pixmap.height - 1)
            color = tuple(channel / 255 for channel in pixmap.pixel(x, y))

            mask_page = masks.new_page(
                width=page_rect.width, height=page_rect.height
            )
            mask_page.draw_rect(redaction["bbox"], color=None, fill=color)
            rectangle = mask_page.get_pixmap(colorspace=fitz.csRGB, alpha=True)
            # Mask out pixels the rectangle does not paint. Both images then
            # contain only its exact rendered footprint, including boundaries.
            mask = fitz.Pixmap(None, rectangle)
            masked = fitz.Pixmap(pixmap, mask)
            # Compare buffers in C while copying only one of the pixmaps.
            if bytearray(masked.samples_mv) == rectangle.samples_mv:
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
