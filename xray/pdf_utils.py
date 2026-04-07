"""
Utilities for working with PDFs and redactions
"""

import re
import typing

import fitz
from fitz import Page, Rect

from .custom_types import CharDictType, PdfRedactionsDict, RedactionType
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


# Matches CM/ECF header stamp text.  These vary by court but always
# contain a document identifier (Doc/Document/DktEntry) and a page
# indicator.  The regex is intentionally loose on spacing and
# punctuation to handle the many formatting variations across courts.
_HEADER_STAMP_RE = re.compile(
    r"(Doc(ument)?|DktEntry).+Filed.+Page", re.IGNORECASE
)


def _is_header_stamp(span: dict) -> bool:
    """Check whether a text span is a CM/ECF header stamp.

    Courts add these stamps (case number, doc number, filing date,
    page number) to every page of a filing.  We require ALL THREE
    of the following to match, to avoid false filtering:

    1. **Position** — The span must be in the header area (y < 43)
       or at the very top of the page (y < 20 for the ca5 exception
       where a different font is used).
    2. **Font** — LiberationSans is the standard CM/ECF stamp font.
       At y < 20, any font is accepted (ca5 exception).
    3. **Content** — The text must match the CM/ECF stamp pattern
       (contains Doc/Document/DktEntry + Filed + Page).

    :param span: A text trace span dict from ``page.get_texttrace()``.
    :returns: True if the span looks like a header stamp.
    """
    y = span["bbox"][1]

    # Position gate: must be near the top of the page
    if y >= 43:
        return False

    # Font gate: require LiberationSans, except at the very top
    # of the page (y < 20) where ca5 uses a different font.
    if y >= 20 and "LiberationSans" not in span.get("font", ""):
        return False

    # Content gate: the text must look like a CM/ECF stamp
    text = "".join(chr(c[0]) for c in span["chars"])
    return bool(_HEADER_STAMP_RE.search(text))


def get_content_spans(page: Page) -> list[dict]:
    """Get text spans from a page, excluding court header stamps.

    CM/ECF header stamps (case number, doc number, filing date, page
    number) appear on every page of a court filing and are a common
    source of false positives.  This function filters them out before
    the intersection stage so downstream code doesn't need to know
    about them.

    :param page: The PyMuPDF.Page object to inspect.
    :returns: The filtered list of text trace span dicts.
    """
    return [s for s in page.get_texttrace() if not _is_header_stamp(s)]


def get_intersecting_chars(
    spans: list[dict], rectangles: list[Rect]
) -> list[CharDictType]:
    """Get the chars that are occluded by the rectangles

    We do this in two stages. First, we check for intersecting spans, then we
    check for intersecting chars within those spans. The idea of this is

    :param spans: Text trace spans from ``get_content_spans``.
    :param rectangles: A list of PyMuPDF.Rect objects from the page (aka the
    redactions).
    :return A list of characters that are under the rectangles
    """
    if len(rectangles) == 0:
        return []

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


def _is_dark_color(
    color: tuple[int, ...],
    luminance_threshold: int = 100,
) -> bool:
    """Check whether an RGB color is dark enough to be a redaction.

    Redactions are meant to hide text, so they use dark colors (black,
    dark gray, dark navy).  Bright colors — teal sidebars, yellow
    highlights, orange slide elements — are design elements.

    Also rejects white (all channels 255), which indicates a white
    rectangle on a white page background (form fields, layout
    elements — see GitHub issue #196).

    Uses ITU-R BT.601 perceived luminance on a 0–255 scale::

        black (0,0,0)→0  dark gray (34,31,31)→32
        teal (0,173,198)→124  yellow (255,255,0)→227

    :param color: An RGB tuple with integer channels 0–255.
    :param luminance_threshold: Maximum perceived brightness for a
        color to be considered "dark enough" for a redaction.
    :returns: True if the color is dark (plausible redaction).
    """
    if all(c == 255 for c in color):
        return False
    luminance = 0.299 * color[0] + 0.587 * color[1] + 0.114 * color[2]
    return luminance <= luminance_threshold


def filter_redactions_by_pixmap(
    redactions: list[RedactionType],
    page: Page,
) -> list[RedactionType]:
    """Filter candidate redactions by rendering each as a pixmap.

    A bad redaction is a solid, dark-colored rectangle hiding text.
    This function renders each candidate region and checks two things:

    1. **Uniformity** — Is the rendered area (nearly) one color?  If
       not, the rectangle contains visible content and isn't hiding
       anything.  Uses ``_is_nearly_unicolor`` which tolerates slight
       rendering variations (e.g., two dark grays differing by 1 per
       channel) and ignores a 1px edge border where stray pixels from
       rounded corners commonly appear.

    2. **Darkness** — Is that uniform color dark?  White rectangles
       are form fields; bright colors (teal, yellow, orange) are
       design elements.  Only dark colors indicate a redaction.

    :param redactions: A list of redactions that might be bad
    :param page: The PyMuPDF.Page object where the bad redactions
        might be
    :return: The redactions that are actually bad
    """
    bad_redactions = []
    for redaction in redactions:
        pixmap = page.get_pixmap(
            colorspace=fitz.csRGB,
            clip=fitz.Rect(redaction["bbox"]),
        )
        # Guard against degenerate pixmaps (zero width or height).
        # PyMuPDF can produce these from certain clip rectangles and
        # segfaults if you then access is_unicolor or samples.
        if pixmap.width == 0 or pixmap.height == 0:
            continue
        nearly_uniform, dominant = _is_nearly_unicolor(pixmap)
        if not nearly_uniform:
            continue
        assert dominant is not None  # guaranteed when nearly_uniform
        if not _is_dark_color(dominant):
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


def get_dark_highlight_annotations(page: Page) -> list[RedactionType]:
    """Find dark Highlight annotations used as makeshift redactions.

    Some documents use black (or very dark) Highlight annotations to
    obscure text instead of proper redaction tools.  The text remains
    fully readable and extractable underneath.  We only flag dark
    highlights — bright-colored highlights (yellow, green, pink) are
    legitimate markup, not redaction attempts.

    :param page: The PyMuPDF Page to look for annotations within.
    :returns: A list of RedactionType dicts for each dark highlight
    annotation that contains text within the visible page area.
    """
    redactions = []
    for annot in page.annots() or []:
        if annot.type[0] != fitz.PDF_ANNOT_HIGHLIGHT:
            continue

        # Check if the highlight stroke color is dark.  Highlight
        # annotations use "stroke" (not "fill") for their color.
        stroke = annot.colors.get("stroke")
        if not stroke:
            continue
        # Convert from 0–1 float range to 0–255 for _is_dark_color
        rgb_255 = tuple(int(c * 255) for c in stroke)
        if not _is_dark_color(rgb_255):
            continue

        annot_rect = annot.rect
        if not annot_rect.intersects(page.rect):
            continue

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


def _is_x_hatch_drawing(drawing: dict) -> bool:
    """Check whether a drawing is an X-hatch (cross-hatch) pattern.

    In the PDF structure, each X is two diagonal lines tiled across
    the redacted area.  A single drawing contains all the X's as
    pairs of "l" (line) items.  For example, an X spanning x=100–117
    would be stored as::

        ("l", Point(100, bottom), Point(117, top))   # ╲ diagonal
        ("l", Point(100, top),    Point(117, bottom)) # ╱ diagonal

    We identify this pattern by checking that:
    1. The drawing consists entirely of "l" items (no rects, curves).
    2. There's an even number of items (they come in pairs).
    3. Each pair shares the same x-range (both diagonals start and
       end at the same horizontal positions, within 1pt tolerance
       for floating-point rounding).

    :param drawing: A drawing dict from ``page.get_drawings()``.
    :returns: True if the drawing is an X-hatch pattern.
    """
    items = drawing["items"]

    # Must have at least one pair, and an even count
    if len(items) < 2 or len(items) % 2 != 0:
        return False

    # Every item must be a line — no rectangles, curves, or quads
    if not all(item[0] == "l" for item in items):
        return False

    # Each consecutive pair must share the same x-range, meaning
    # both lines start at the same x and end at the same x.  This
    # is what makes them cross (╲╱) rather than parallel (╲╲).
    for i in range(0, len(items), 2):
        l1_start, l1_end = items[i][1], items[i][2]
        l2_start, l2_end = items[i + 1][1], items[i + 1][2]
        if abs(l1_start.x - l2_start.x) > 1:
            return False
        if abs(l1_end.x - l2_end.x) > 1:
            return False
    return True


def get_cross_hatched_redactions(page: Page) -> list[RedactionType]:
    """Find text hidden under cross-hatched (X-pattern) redactions.

    Some documents use a repeating X pattern drawn over dark
    rectangles to redact text.  The normal pixmap-based detection
    can't catch these because the cross-hatching creates two colors
    in the rendered area (e.g., black at 86% + dark gray at 14%),
    which fails the ``_is_nearly_unicolor`` check.

    Instead of analyzing pixels, we detect X-hatch patterns directly
    from the PDF drawing structure using ``_is_x_hatch_drawing``,
    then extract whatever text sits underneath them.  The results
    still go through ``filter_redactions_by_text`` in the pipeline
    to remove false positives like repeated characters.

    :param page: The PyMuPDF Page to inspect.
    :returns: A list of RedactionType dicts for text under X-hatches.
    """
    drawings = page.get_drawings()
    x_hatches = [d for d in drawings if _is_x_hatch_drawing(d)]
    if not x_hatches:
        return []

    redactions = []
    for xh in x_hatches:
        # Use the bounding box of the X-hatch drawing to clip text
        # extraction.  This may include a few characters from
        # adjacent unredacted text; the text filters downstream
        # handle that.
        xh_rect = fitz.Rect(xh["rect"])
        text = page.get_text("text", clip=xh_rect)
        text = " ".join(text.split())
        if text:
            redaction: RedactionType = {
                "bbox": (xh_rect.x0, xh_rect.y0, xh_rect.x1, xh_rect.y1),
                "text": text,
            }
            redactions.append(redaction)

    return redactions


def get_image_redactions(page: Page) -> list[RedactionType]:
    """Find text hidden under dark images used as redaction overlays.

    Some documents place a solid black (or dark) raster image on top
    of text instead of using a proper vector rectangle or redaction
    tool.  The image hides the text visually, but the text layer
    remains intact and extractable underneath.

    We detect these by examining each image on the page:

    1. Render the page at the image's bounding box.
    2. Check if the rendered area is (nearly) unicolor and dark.
       This is the ground truth of what the viewer sees — it also
       correctly ignores dark images drawn *behind* other elements
       (form backgrounds, template layers) where the text is still
       visible on the rendered page.
    3. If the rendered area is dark, extract any text underneath.

    Images that are large relative to the page (>50% of page area)
    are skipped — these are likely full-page scanned backgrounds,
    not targeted redaction overlays.

    :param page: The PyMuPDF Page to inspect.
    :returns: A list of RedactionType dicts for text under dark images.
    """
    page_area = abs(page.rect)
    redactions = []

    # get_image_info is much cheaper than get_text("dict") because
    # it returns only image metadata without parsing all text blocks.
    for img in page.get_image_info():
        bbox = fitz.Rect(img["bbox"])

        # Skip images that cover most of the page — these are
        # scanned page backgrounds, not redaction overlays.
        if abs(bbox) > 0.5 * page_area:
            continue

        # Skip tiny images (likely bullets, icons, etc.)
        if bbox.width < 10 or bbox.height < 5:
            continue

        # Render the page at this location and check if the result
        # is a dark, uniform area.  This is the ground truth of what
        # the viewer sees — it catches both:
        # - Dark images on top of text (bad redaction)
        # - Dark images behind other elements (not a redaction,
        #   because the rendered page shows the content on top)
        page_pix = page.get_pixmap(colorspace=fitz.csRGB, clip=bbox)
        if page_pix.width == 0 or page_pix.height == 0:
            continue
        nearly_uniform, dominant = _is_nearly_unicolor(page_pix)
        if not nearly_uniform:
            continue
        assert dominant is not None
        if not _is_dark_color(dominant):
            continue

        # Dark unicolor rendered area — extract text underneath
        text = page.get_text("text", clip=bbox)
        text = " ".join(text.split())
        if text:
            redaction: RedactionType = {
                "bbox": (bbox.x0, bbox.y0, bbox.x1, bbox.y1),
                "text": text,
            }
            redactions.append(redaction)

    return redactions


def get_redaction_bboxes(page: Page) -> list[tuple[float, ...]]:
    """Collect bounding boxes of all redaction-shaped objects on a page.

    This gathers the locations of everything that *looks* like a
    redaction: dark rectangles, dark images, dark highlight annotations,
    cross-hatch patterns, and unapplied Redact annotations.  The result
    is used both for bad-redaction detection (is there text underneath?)
    and for TOC leak detection (does a bookmark point here?).

    Collecting these once avoids repeating expensive operations like
    drawing extraction, image inspection, and pixmap rendering.

    :param page: The PyMuPDF.Page to inspect.
    :returns: A list of (x0, y0, x1, y1) bounding box tuples.
    """
    bboxes: list[tuple[float, ...]] = []

    # Dark filled rectangles (vector drawings)
    for rect in get_good_rectangles(page):
        bboxes.append((rect.x0, rect.y0, rect.x1, rect.y1))

    # Unapplied Redact annotations
    for r in get_unapplied_redact_annotations(page):
        bboxes.append(r["bbox"])

    # Dark Highlight annotations
    for r in get_dark_highlight_annotations(page):
        bboxes.append(r["bbox"])

    # Cross-hatched (X-pattern) drawings
    for r in get_cross_hatched_redactions(page):
        bboxes.append(r["bbox"])

    # Dark images used as overlays
    for r in get_image_redactions(page):
        bboxes.append(r["bbox"])

    # X-replacement text (e.g., "XXXXXXXXX").  These aren't visual
    # objects like rectangles or images, but they indicate that
    # someone replaced a name/word with X's.  We find their bboxes
    # via text search so TOC leak detection can match against them.
    for block in page.get_text("dict")["blocks"]:
        if block["type"] != 0:  # text block
            continue
        for line in block["lines"]:
            for span in line["spans"]:
                if re.search(r"X{3,}", span["text"], re.IGNORECASE):
                    bboxes.append(tuple(span["bbox"]))

    return bboxes


def get_bad_redactions(page: Page) -> list[RedactionType]:
    """Get the bad redactions for a page from a PDF.

    :param page: The PyMuPDF.Page from a PDF.
    :returns: A list of redaction dicts with bbox and text keys.
    """
    # --- Rectangle-based detection (text under dark bars) ---
    good_rectangles = get_good_rectangles(page)
    content_spans = get_content_spans(page)
    intersecting_chars = get_intersecting_chars(content_spans, good_rectangles)
    redactions = group_chars_by_rect(intersecting_chars, good_rectangles)
    bad_redactions = filter_redactions_by_text(redactions)
    bad_redactions = filter_redactions_by_pixmap(bad_redactions, page)

    # --- Annotation-based detection ---
    unapplied = get_unapplied_redact_annotations(page)
    unapplied = filter_redactions_by_text(unapplied)
    bad_redactions.extend(unapplied)

    highlights = get_dark_highlight_annotations(page)
    highlights = filter_redactions_by_text(highlights)
    bad_redactions.extend(highlights)

    # --- Pattern-based detection ---
    cross_hatched = get_cross_hatched_redactions(page)
    cross_hatched = filter_redactions_by_text(cross_hatched)
    bad_redactions.extend(cross_hatched)

    # --- Image-based detection ---
    image_redactions = get_image_redactions(page)
    image_redactions = filter_redactions_by_text(image_redactions)
    bad_redactions.extend(image_redactions)

    return bad_redactions


def get_toc_leaks(
    doc: fitz.Document,
    redaction_bboxes_by_page: dict[int, list[tuple[float, ...]]],
) -> PdfRedactionsDict:
    """Find bookmark/TOC entries that leak redacted content.

    When someone redacts text in a heading (with a black bar, image,
    or by applying a proper redaction), they sometimes forget to also
    sanitize the PDF bookmarks.  The bookmark still contains the
    original heading text, revealing what was redacted.

    This function spatially matches bookmark targets against
    redaction-shaped objects already found by
    ``get_redaction_bboxes``.  This reuses the expensive detection
    work (drawing extraction, image inspection, pixmap rendering)
    that was already done for bad-redaction detection, so we don't
    process the document twice.

    For each TOC entry we check:

    1. Does a redaction-shaped object on the target page overlap
       the bookmark's y-position (within 20pt tolerance)?
    2. Does the bookmark title contain words not found on the page?

    If both are true, the bookmark is leaking redacted content.

    :param doc: The PyMuPDF Document to inspect.
    :param redaction_bboxes_by_page: Redaction-shaped bboxes per
        page (1-based keys), from ``get_redaction_bboxes``.
    :returns: A PdfRedactionsDict with TOC leak entries.
    """
    toc = doc.get_toc(simple=False)
    if not toc:
        return {}

    redactions: dict[int, list[RedactionType]] = {}
    for _level, title, _page_num_1based, dest in toc:
        if not dest or "page" not in dest:
            continue

        # page can be an int or a string depending on the PDF
        try:
            page_idx = int(dest["page"])
        except (ValueError, TypeError):
            continue
        if page_idx < 0 or page_idx >= len(doc):
            continue

        page_key = page_idx + 1  # 1-based

        # Get the bookmark's target y-coordinate.  Some bookmarks
        # use "Fit" view mode and don't have a "to" point — skip
        # these since we can't verify the location.
        target = dest.get("to")
        if target is None:
            continue
        bookmark_y = target.y

        # Check if any redaction-shaped object on this page
        # overlaps the bookmark's target y-position.  Without this
        # spatial guard, normal bookmarks referencing slides or
        # images produce false positives.
        y_tolerance = 20  # points
        page_bboxes = redaction_bboxes_by_page.get(page_key, [])
        has_redaction_at_heading = any(
            bbox[1] - y_tolerance <= bookmark_y <= bbox[3] + y_tolerance
            for bbox in page_bboxes
        )
        if not has_redaction_at_heading:
            continue

        # Check if the bookmark title contains words not found on
        # the page.  Any word present in the bookmark but absent
        # from the page text was likely redacted — and the bookmark
        # is leaking it.
        page = doc[page_idx]
        page_text = page.get_text("text")
        leaked_words = [
            w
            for w in re.split(r"[\s.,;:!?]+", title)
            if w and w not in page_text
        ]
        if not leaked_words:
            continue

        leak: RedactionType = {
            "bbox": (target.x, target.y, target.x, target.y),
            "text": title,
        }
        redactions.setdefault(page_key, []).append(leak)

    return redactions
