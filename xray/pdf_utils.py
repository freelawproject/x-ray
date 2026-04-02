"""
Utilities for working with PDFs and redactions
"""

import re
import typing

import fitz
from fitz import Page, Rect

from .custom_types import CharDictType, RedactionType
from .text_utils import is_ok_words, is_repeated_chars, is_single_char

# Disable anti-aliasing when rendering and creating pixmaps
fitz.TOOLS.set_aa_level(0)


def get_good_rectangles(page: Page) -> list[Rect]:
    """Find rectangles in the PDFs that might be redactions.

    :param page: The PyMuPDF Page to look for rectangles within.
    :returns A list of PyMUPDF.Rect objects for each fully opaque rectangle
    that's big enough to be a possible redaction. If none, returns
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
        rectangles = [item[1] for item in drawing["items"] if item[0] == "re"]

        if not rectangles:
            # Some redaction tools draw rounded rectangles using lines
            # ("l") and bezier curves ("c") instead of the "re" draw
            # command.  These shapes have no "re" items, but the
            # drawing's outer "rect" key gives us a usable bounding
            # box.
            #
            # It is safe to fall back to drawing["rect"] here because
            # the multi-line redaction problem described above only
            # occurs when a single drawing contains multiple "re"
            # items whose combined bounding box is wider than each
            # individual bar.  A drawing with zero "re" items is a
            # single shape, so its bounding box is correct.
            rectangles = [fitz.Rect(drawing["rect"])]

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

    overlapping_areas = []
    for rect in rectangles:
        intersecting_area = abs(text_rect & rect)
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
    page: Page, rectangles: list[Rect]
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

    spans = page.get_texttrace()
    intersecting_chars = []
    for span in spans:
        span_seq_no = span["seqno"]
        span_color = span["color"]
        span_rect = fitz.Rect(span["bbox"])
        span_rect.seqno = span_seq_no
        span_rect.fill = span_color
        if not intersects(span_rect, rectangles):
            continue
        for char in span["chars"]:
            char_rect = fitz.Rect(char[3])
            char_rect.seqno = span_seq_no
            char_rect.fill = span_color
            if intersects(char_rect, rectangles, occlusion_threshold=0.8):
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
        # Make a copy of the chars list so we can manipulate it in the loop
        char_copy = chars.copy()
        for char in char_copy:
            if abs(char["rect"] & rect):
                # The char intersects with this rectangle. Add it to the
                # redaction dict, and remove it from the list so it doesn't
                # get analyzed again.
                redaction["text"] += char["c"]
                chars.remove(char)
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

    # Isn't just a single character (possibly with whitespace/punctuation)
    redactions = filter(lambda r: not is_single_char(r["text"]), redactions)

    # Has non-whitespace content and isn't blank
    redactions = filter(lambda r: r["text"].strip(), redactions)

    # Has some letters or numbers (isn't just a rectangle
    # with nothing under it)
    redactions = filter(lambda r: re.search(r"[\d\w]", r["text"]), redactions)

    # Has OK words in redaction
    redactions = filter(lambda r: is_ok_words(r["text"]), redactions)

    # Doesn't contain Unicode replacement characters (U+FFFD).  These
    # appear when a PDF uses a custom font encoding that PyMuPDF can't
    # decode.  The extracted "text" is encoding gibberish, not readable
    # content, so it's not a meaningful redaction.
    redactions = filter(lambda r: "\ufffd" not in r["text"], redactions)

    return list(redactions)


def _is_nearly_unicolor(
    pixmap: fitz.Pixmap,
    tolerance: int = 5,
) -> tuple[bool, tuple[int, ...] | None]:
    """Check if a pixmap is nearly uniform in color.

    Some PDFs render solid redaction bars with slight color
    variations (e.g., two shades of dark gray differing by 1 per
    channel). PyMuPDF's is_unicolor misses these.

    To handle this while avoiding false positives from visible text
    on colored backgrounds, this function checks the interior pixels
    (excluding a 1px border) for uniformity within ``tolerance``.
    Edge pixels are excluded because rendering artifacts (stray
    white pixels) commonly appear at rectangle boundaries.

    :param pixmap: The pixmap to check.
    :param tolerance: Max per-channel difference from the first
    interior pixel for another pixel to count as matching.
    :returns: A (is_uniform, dominant_color) tuple. dominant_color
    is None when is_uniform is False.
    """
    # Fast path: PyMuPDF's native check handles the common case of
    # a perfectly uniform pixmap (e.g., a solid black bar).
    if pixmap.is_unicolor:
        return True, pixmap.pixel(0, 0)

    w, h = pixmap.width, pixmap.height
    if w <= 2 or h <= 2:
        # Too small to have a meaningful interior after excluding
        # the 1px border — bail out conservatively.
        return False, None

    samples = pixmap.samples
    n = pixmap.n  # bytes per pixel (3 for RGB, 4 for RGBA)

    # Walk only the interior pixels (skip the 1px border on every
    # side).  The first interior pixel becomes the reference color;
    # every subsequent pixel must be within ``tolerance`` of it on
    # every channel.
    #
    # Why exclude the border?  When PyMuPDF renders a clipped region
    # at 72 DPI with anti-aliasing disabled, stray white pixels
    # frequently appear along the edges of the clip rectangle.
    # These are rendering artifacts, not content, and including them
    # would cause truly solid bars to fail the uniformity check.
    ref = None
    for y in range(1, h - 1):
        for x in range(1, w - 1):
            offset = (y * w + x) * n
            pixel = tuple(samples[offset : offset + n])
            if ref is None:
                ref = pixel
            elif any(abs(a - b) > tolerance for a, b in zip(pixel, ref)):
                # Found an interior pixel that differs meaningfully
                # from the reference — this pixmap contains visible
                # content (e.g., text rendered on a colored
                # background), not just a solid bar.
                return False, None
    return True, ref


def filter_redactions_by_pixmap(
    redactions: list[RedactionType],
    page: Page,
) -> list[RedactionType]:
    """Convert each bad redaction to an image and check it for text

    :param redactions: A list of redactions that might be bad
    :param page: The PyMuPDF.Page object where the bad redactions might be
    :return: The redactions, if they are valid
    """
    bad_redactions = []
    for redaction in redactions:
        pixmap = page.get_pixmap(
            # Use gray for simplicity and speed, though this risks missing a
            # bad redaction.
            colorspace=fitz.csRGB,
            clip=fitz.Rect(redaction["bbox"]),
        )
        nearly_uniform, dominant = _is_nearly_unicolor(pixmap)
        if not nearly_uniform:
            # The interior pixels vary meaningfully — the rendered
            # region contains visible content (text, patterns, etc.)
            # on top of the rectangle.  ∴ it's not a uniform box
            # hiding text and it's not a bad redaction.
            #
            # This replaces the old ``pixmap.is_unicolor`` check,
            # which was too strict: some PDFs render solid redaction
            # bars as two nearly-identical dark colors (e.g.,
            # RGB(34,31,31) and RGB(35,31,32)), causing PyMuPDF to
            # consider them non-uniform even though they are visually
            # indistinguishable.
            continue
        # The pixmap is (nearly) uniform.  Now check whether that
        # uniform color is white: a white rectangle on a white page
        # background means the text is already visually invisible.
        # These are typically form fields or layout elements, not
        # intentional redaction attempts, and are a common source of
        # false positives (see GitHub issue #196).
        assert dominant is not None  # guaranteed when nearly_uniform is True
        if all(c == 255 for c in dominant):
            continue
        # Check if the dominant color is too bright to be a redaction.
        # Redactions are meant to hide text, so they're almost always
        # dark (black, dark gray, dark navy).  Bright colors like teal,
        # yellow, orange, or green are design elements (sidebars, slide
        # backgrounds, decorative bars), not redaction attempts.
        #
        # We use perceived luminance (ITU-R BT.601) on a 0–255 scale:
        #   black (0,0,0) → 0,  dark gray (34,31,31) → 32,
        #   teal (0,173,198) → 124,  yellow (255,255,0) → 227
        #
        # A threshold of 100 is generous enough to keep even dark
        # blue/navy bars while filtering anything clearly colored.
        r, g, b = dominant[0], dominant[1], dominant[2]
        luminance = 0.299 * r + 0.587 * g + 0.114 * b
        if luminance > 100:
            continue
        bad_redactions.append(redaction)
    return bad_redactions


def get_unapplied_redact_annotations(page: Page) -> list[RedactionType]:
    """Find Redact annotations that haven't been applied.

    Unapplied Redact annotations mark text for redaction but leave the text
    visible and extractable. These are bad redactions because the text that
    was supposed to be hidden is still readable.

    :param page: The PyMuPDF Page to look for annotations within.
    :returns: A list of RedactionType dicts for each unapplied redaction
    annotation that contains text within the visible page area.
    """
    redactions = []
    for annot in page.annots() or []:
        if annot.type[0] != fitz.PDF_ANNOT_REDACT:
            continue

        annot_rect = annot.rect
        if not annot_rect.intersects(page.rect):
            continue

        # Clip to visible area
        visible_rect = annot_rect & page.rect
        text = page.get_text("text", clip=visible_rect)
        text = " ".join(text.split())
        if text:
            redaction: RedactionType = {
                "bbox": (
                    visible_rect.x0,
                    visible_rect.y0,
                    visible_rect.x1,
                    visible_rect.y1,
                ),
                "text": text,
            }
            redactions.append(redaction)

    return redactions


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

    # Also detect unapplied Redact annotations
    unapplied = get_unapplied_redact_annotations(page)
    unapplied = filter_redactions_by_text(unapplied)
    bad_redactions.extend(unapplied)

    return bad_redactions
