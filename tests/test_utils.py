"""
X-Ray Tests
"""

import os
import unittest
from pathlib import Path
from unittest import TestCase

import fitz
from fitz import Rect

import xray
from xray.custom_types import BadRedactionType
from xray.pdf_utils import (
    get_bad_redactions,
    get_content_spans,
    get_good_rectangles,
    get_intersecting_chars,
    intersects,
)
from xray.text_utils import looks_like_a_date

root_path = Path(__file__).resolve().parent / "assets"


class TextTest(TestCase):
    """Do our text tools work properly?"""

    def test_valid_date_only_checks(self):
        actual_dates = (
            "12/13/21",
            "12/14/2111",
            "1/1/22",
            "1/1/2022",
            "01-02/2222",  # Fine, whatever
            "03/23/",  # Truncated at rectangle boundary
            "03/23",  # No year at all
            "03/23/201",  # Partial year
        )
        for d in actual_dates:
            with self.subTest(d):
                self.assertTrue(looks_like_a_date(d))

    def test_invalid_date_only_checks(self):
        not_dates = (
            "111/11/11",
            "asdf-",
            "asdf 1/1/2022",
        )

        for d in not_dates:
            with self.subTest(d):
                self.assertFalse(looks_like_a_date(d))


class RectTest(TestCase):
    """Do our rectangle-finding utilities work properly?"""

    def test_we_find_rectangles_when_we_should(self):
        paths = (
            root_path / "rectangles_yes.pdf",
            root_path / "rectangles_yes_2.pdf",
        )
        for path in paths:
            with fitz.open(path) as pdf, self.subTest(f"{path=}"):
                page = pdf[0]
                self.assertTrue(get_good_rectangles(page))

    def test_we_do_not_find_rectangles_when_we_should_not(self):
        path = root_path / "rectangles_no.pdf"
        with fitz.open(path) as pdf:
            page = pdf[0]
            self.assertFalse(get_good_rectangles(page))


def rectangle_factory(
    bbox: tuple[float, ...], seqno: int, fill: float
) -> Rect:
    """Factory for making little rectangles with extra attributes"""
    r = Rect(*bbox)
    r.seqno = seqno
    r.fill = fill
    return r


class IntersectionTest(TestCase):
    """Do rectangles intersect properly?"""

    rect = rectangle_factory(
        (1, 1, 2, 2),
        seqno=0,  # All other rectangles are on top!
        fill=1,
    )

    def test_in_one_of_many(self):
        """Does a bbox inside of one, but not all rectangles intersect?"""
        self.assertTrue(
            intersects(
                self.rect,
                [
                    rectangle_factory((0.5, 0.5, 3, 3), 1, 1),
                    rectangle_factory((3, 3, 4, 4), 1, 1),
                ],
            )
        )

    def test_not_in_any(self):
        """Do we return False when things don't intersect?"""
        self.assertFalse(
            intersects(
                self.rect,
                [
                    rectangle_factory((3, 3, 4, 4), 1, 1),
                    rectangle_factory((4, 4, 5, 5), 1, 1),
                ],
            )
        )

    def test_in_all(self):
        """Do we return True when the bbox is in all the rects?"""
        self.assertTrue(
            intersects(
                self.rect,
                [
                    rectangle_factory((0.5, 0.5, 3, 3), 1, 1),
                    rectangle_factory((0.6, 0.6, 4, 4), 1, 1),
                ],
            )
        )

    def test_partial_intersection(self):
        """Do we return true when only corners intersect?"""
        self.assertTrue(
            intersects(
                self.rect,
                [rectangle_factory((0.5, 0.5, 1.5, 1.5), 1, 1)],
            )
        )


class OcclusionTest(TestCase):
    """Can we get a list of bad redactions?"""

    def test_finding_bad_redactions(self):
        path = root_path / "rectangles_yes.pdf"
        with fitz.open(path) as pdf:
            page = pdf[0]
            chars = get_intersecting_chars(
                get_content_spans(page), get_good_rectangles(page)
            )
        self.assertEqual(len(chars), 64)

    def test_cross_hatched_redactions(self):
        """Are cross-hatched (X-pattern) redactions detected?"""
        path = root_path / "bad_cross_hatched_redactions.pdf"
        redactions = xray.inspect(path)
        self.assertEqual(
            len(redactions.get(1, [])),
            16,
            msg=f"Expected 16 cross-hatched redactions, "
            f"got {len(redactions.get(1, []))}.",
        )

    def test_ignoring_partial_occlusions(self):
        path = root_path / "partial_intersections_ok.pdf"
        with fitz.open(path) as pdf:
            page = pdf[0]
            chars = get_intersecting_chars(
                get_content_spans(page), get_good_rectangles(page)
            )
        self.assertEqual(len(chars), 0)

    @unittest.expectedFailure
    def test_overlapping_text(self):
        """Do we find bad redactions with visible text below them?

        This test case is a nasty one. If you look closely at LLC with your
        cursor or, even better, at TROPPER in the heading, you'll see that
        there is hidden text on top of the visible text. TROPPER is fun because
        the hidden text is the correctly spelled word, "TROOPER."

        Anyway, for now we don't support this at all, because our pixmap
        approach sees the visible text below the hidden text, and thinks that
        there's no bad redaction there. Someday, we should fix this, but it
        seems very difficult.
        """
        path = root_path / "hidden_text_on_visible_text.pdf"
        redactions = xray.inspect(path)
        expected_redaction_count = 2
        self.assertEqual(
            len(list(redactions.values())),
            expected_redaction_count,
        )

    def test_text_on_rectangles_ok(self):
        """Is text on top of an opaque rectangles, wrongly marked as a bad
        redaction?
        """
        # Files selected randomly. Each is numbered sequentially. The number
        # represents the page number from the original doc that these are
        # sampled from.
        paths = (
            "rect_ordering_0.8.pdf",
            "rect_ordering_1.23.pdf",
            "rect_ordering_2.1.pdf",
            "rect_ordering_3.20.pdf",
            "rect_ordering_4.1.pdf",
            "rect_ordering_5.2.pdf",
            "rect_ordering_6.19.pdf",
        )
        for path in paths:
            path = root_path / path
            with self.subTest(f"{path=}"):
                with fitz.open(path) as pdf:
                    page = pdf[0]
                    chars = get_bad_redactions(page)
                self.assertEqual(
                    len(chars),
                    0,
                    msg=f"Got bad redaction when no redaction present: {chars}",
                )


class InspectApiTest(TestCase):
    """Does the API of the inspect method work properly?"""

    def test_inspect_works_with_path_or_str(self):
        path_str = "rectangles_yes.pdf"
        paths = (
            root_path / path_str,
            os.path.join(str(root_path), path_str),
        )
        for path in paths:
            redactions = xray.inspect(path)
            self.assertTrue(redactions)

    def test_inspect_works_with_bytes(self):
        path = root_path / "rectangles_yes.pdf"
        with open(path, "rb") as f:
            data = f.read()

        redactions = xray.inspect(data)
        self.assertTrue(redactions)


class IntegrationTest(TestCase):
    """Do our highest-level APIs work?"""

    path = root_path / "rectangles_yes.pdf"

    def test_bad_redactions_on_single_page(self):
        with fitz.open(self.path) as pdf:
            page = pdf[0]
            bad_redactions = get_bad_redactions(page)
        expected_bad_redaction_count = 3
        actual_bad_redaction_count = len(bad_redactions)
        self.assertEqual(
            actual_bad_redaction_count,
            expected_bad_redaction_count,
            msg=f"Got {actual_bad_redaction_count} bad redactions, but "
            f"expected {expected_bad_redaction_count}. Redaction data is: "
            f"{bad_redactions}",
        )

    def test_inspect_method_on_a_filepath(self):
        redactions = xray.inspect(self.path)
        self.assertEqual(len(redactions[1]), 3)
        # All redactions in this file are text under rectangles
        for r in redactions[1]:
            self.assertEqual(r["type"], BadRedactionType.TEXT_UNDER_RECTANGLE)

    def test_tricky_rectangles(self):
        """Check that tricky PDFs don't create false positives.

        These are a variety of tough cases that don't have redactions, but
        which can appear to due to their complexity. When our approach uses
        only rectangles and text from parsing the PDF, each of these examples
        comes back as a false positive. To fix this, we render the relevant
        part of the document as a pixmap and then analyze that for more than
        one color in the box. If we see multiple colors, we know that it's not
        a bad redaction.

        Note that any of these weird PDFs can be inspected with:

            mutools trace some-doc.pdf
        """
        self.maxDiff = None

        # The first digit in these file names is just a counter for the
        # example. The second is the page in the original it was pulled from
        # or the page in the current one (if multi-page) where it caused an
        # issue.
        paths = (
            # The red rectangles in this document are complicated due to
            # non-zero winding rules:
            #
            #   https://en.wikipedia.org/wiki/Nonzero-rule
            #
            # In short, when paths in a drawing overlap, you need a method of
            # figuring out which enclosed parts of the drawing are filled
            # (inside the drawing), and which are not (outside the drawing).
            #
            # PyMuPDF doesn't have a way of determining that at present, so
            # when we look at the two squares in this PDF, it looks like the
            # text that the squares surround is inside of them. That's
            # intuitively true, but due to the winding rules, the surrounded
            # part is actually not inside the drawing, and that's why that part
            # of the rectangles is transparent, not red. In fact, the center of
            # the rectangle is outside of the drawing, and despite the drawing
            # and the text occupying the same x-y space, one does not occlude
            # the other (note that you can plainly see the text).
            #
            # More discussion: https://github.com/pymupdf/PyMuPDF/issues/1355
            "no_bad_redactions.2.1.pdf",
            "no_bad_redactions.3.1.pdf",
            # A white rectangle in this drawing occupies the same location as
            # the text across the top due clipping paths.
            #
            # See: https://github.com/pymupdf/PyMuPDF/issues/1387
            "no_bad_redactions.3.2.pdf",
            "no_bad_redactions.4.1.pdf",
            # Lots of messy stuff starting on page five. The word "Article"
            # says it's white, but it appears black when rendered. Don't know
            # why. Yanking off page 5 using pdftk changes the structure of this
            # one, so it gets to have multiple pages in the test case.
            "no_bad_redactions.5.5.pdf",
            "no_bad_redactions.6.2.pdf",
            # The JS-6 rectangle causes issues
            "no_bad_redactions.7.1.pdf",
            # This one has a big image covering literally everything else, and
            # the image appears to have black rectangles. This doesn't have bad
            # redactions b/c the text under the image is just dates, which are
            # fine. Each text box appears to be wrapped in four lines forming
            # a visible rectangle (but not a Rect object). This test case is
            # important for if we ever start dealing with images in the PDFs,
            # because it should continue *not* having bad redactions. (That'll
            # need to be fixed by handling dates though, probably.)
            "no_bad_redactions.8.1.pdf",
        )
        for path in paths:
            path = root_path / path
            with self.subTest(f"{path=}"):
                redactions = xray.inspect(path)
                self.assertEqual(
                    redactions,
                    {},
                    msg="Didn't get empty dict when there were no redactions.",
                )

    def test_whitespace_only_redaction_no_results(self):
        """Do we ignore redactions containing only whitespace chars?"""
        paths = (
            "whitespace_redactions.pdf",
            "whitespace_redactions_2.pdf",
            "whitespace_redaction_with_comma.pdf",
        )
        for path in paths:
            redactions = xray.inspect(root_path / path)
            self.assertEqual(
                redactions,
                {},
                msg="Didn't get empty dict when encountering exclusively "
                "whitespace-filled redactions.",
            )

    def test_unfilled_rect(self):
        """Do unfilled boxes (with only borders and no fill) get ignored?"""
        path = root_path / "unfilled_rect.pdf"
        redactions = xray.inspect(path)
        self.assertEqual(
            redactions,
            {},
            msg="Got redactions 'under' an unfilled rectangle.",
        )

    def test_ok_words_not_redacted(self):
        path = root_path / "ok_words.pdf"
        redactions = xray.inspect(path)
        self.assertEqual(
            redactions,
            {},
            msg="Got redaction even though none in document",
        )

    def test_multiline_redaction(self):
        path = root_path / "multi_line_redaction_ok.pdf"
        redactions = xray.inspect(path)
        self.assertEqual(
            redactions,
            {},
            msg="Got redactions on a multiline redaction, but shouldn't have.",
        )

    def test_white_on_white_no_results(self):
        """Do white rectangles on white backgrounds get ignored?"""
        path = root_path / "white_on_white.pdf"
        redactions = xray.inspect(path)
        self.assertEqual(
            redactions,
            {},
            msg="Got redactions from white-on-white rectangle, "
            "but shouldn't have.",
        )

    def test_repeated_chars_with_spaces_no_results(self):
        """Are repeated chars with spaces filtered? (e.g., 'XXXXX XXXX')"""
        path = root_path / "repeated_chars_with_spaces.pdf"
        redactions = xray.inspect(path)
        self.assertEqual(
            redactions,
            {},
            msg="Got redactions from repeated chars with spaces, "
            "but shouldn't have.",
        )

    def test_short_text_redaction(self):
        """Are short but real redactions (e.g., '34') still detected?"""
        path = root_path / "short_text_redaction.pdf"
        redactions = xray.inspect(path)
        self.assertTrue(
            redactions,
            msg="Expected bad redactions from short text, but got none.",
        )

    def test_cmecf_header_stamp_no_results(self):
        """Are CM/ECF header stamps filtered out?"""
        path = root_path / "cmecf_header_stamp.pdf"
        redactions = xray.inspect(path)
        self.assertEqual(
            redactions,
            {},
            msg="Got redactions from CM/ECF header stamp, but shouldn't have.",
        )

    def test_date_fragments_no_results(self):
        """Are truncated date fragments (e.g., '03/23/') filtered?"""
        path = root_path / "date_fragments.pdf"
        redactions = xray.inspect(path)
        self.assertEqual(
            redactions,
            {},
            msg="Got redactions from date fragments, but shouldn't have.",
        )

    def test_bright_colored_sidebar_no_results(self):
        """Are bright-colored design elements (sidebars, etc.) ignored?"""
        path = root_path / "bright_colored_sidebar.pdf"
        redactions = xray.inspect(path)
        self.assertEqual(
            redactions,
            {},
            msg="Got redactions from bright-colored sidebar, "
            "but shouldn't have.",
        )

    def test_image_behind_text_no_results(self):
        """Are dark images behind text (not covering it) ignored?

        Some PDFs have dark images in the structure that are drawn
        behind other elements. The text is fully visible, so these
        should not be flagged.
        """
        path = root_path / "image_behind_text.pdf"
        redactions = xray.inspect(path)
        self.assertEqual(
            redactions,
            {},
            msg="Got redactions from image behind text, but shouldn't have.",
        )

    def test_toc_leak(self):
        """Do bookmarks pointing to redacted headings get flagged?

        The test PDF has seven pages, each with a different redaction
        type and a TOC entry that leaks the redacted name:

        1. Applied redaction (text removed, black bar left)
        2. Black rectangle over text (bad redaction)
        3. Dark image over text (bad redaction)
        4. X-replacement text (XXXXXXXXXX)
        5. Unapplied Redact annotation
        6. Dark Highlight annotation
        7. No redaction (control — should not leak)
        """
        path = root_path / "toc_leak.pdf"
        redactions = xray.inspect(path)

        all_texts = {
            p: [r["text"] for r in rs] for p, rs in redactions.items()
        }

        # Page 1: applied redaction — TOC leaks the name
        self.assertIn("Report by John Smith", all_texts.get(1, []))
        toc_leak = [
            r
            for r in redactions.get(1, [])
            if r["text"] == "Report by John Smith"
        ][0]
        self.assertEqual(toc_leak["type"], BadRedactionType.TOC_BOOKMARK_LEAK)

        # Page 2: bad redaction — text still extractable
        self.assertTrue(
            any("Doe" in t for t in all_texts.get(2, [])),
        )

        # Page 3: dark image — text still extractable
        self.assertTrue(
            any("Jones" in t for t in all_texts.get(3, [])),
        )

        # Page 4: X-replacement — TOC leaks the name
        self.assertIn("Letter to Sam Wilson", all_texts.get(4, []))

        # Page 5: unapplied Redact — text still extractable
        self.assertTrue(
            any("Carol" in t for t in all_texts.get(5, [])),
        )

        # Page 6: dark highlight — text still extractable
        self.assertTrue(
            any("Foster" in t for t in all_texts.get(6, [])),
        )

        # Page 7: no redaction — nothing should be detected
        self.assertEqual(all_texts.get(7, []), [])

    def test_toc_leak_real(self):
        """Does the JOSH MERRITT declaration leak through the TOC?

        Real-world filing where the name was X'd out on the page and
        covered by black images, but the PDF bookmark still contains
        the original "Declaration of JOSH MERRITT." text.
        """
        path = root_path / "toc_leak_real.pdf"
        redactions = xray.inspect(path)
        all_texts = [r["text"] for rs in redactions.values() for r in rs]
        self.assertTrue(
            any("JOSH" in t and "MERRITT" in t for t in all_texts),
            msg="Expected TOC leak containing 'JOSH MERRITT' "
            "but it wasn't detected.",
        )

    def test_image_redaction(self):
        """Are dark images used as redaction overlays detected?"""
        path = root_path / "image_redaction.pdf"
        redactions = xray.inspect(path)
        self.assertTrue(
            redactions,
            msg="Expected bad redactions from image overlay, but got none.",
        )

    def test_dark_highlight_annotations(self):
        """Are dark Highlight annotations detected as bad redactions?

        Some documents use black Highlight annotations to obscure
        text instead of proper redaction tools.  The text remains
        fully readable underneath.
        """
        path = root_path / "dark_highlight_annotation.pdf"
        redactions = xray.inspect(path)
        self.assertTrue(
            redactions,
            msg="Expected bad redactions from dark highlight "
            "annotations, but got none.",
        )

    def test_custom_font_encoding_no_results(self):
        """Is garbled text from custom font encodings ignored?"""
        path = root_path / "custom_font_encoding.pdf"
        redactions = xray.inspect(path)
        self.assertEqual(
            redactions,
            {},
            msg="Got redactions from undecodable font encoding, "
            "but shouldn't have.",
        )

    def test_redacted_label_no_results(self):
        """Is the word 'REDACTED' under a black bar ignored?"""
        path = root_path / "redacted_label.pdf"
        redactions = xray.inspect(path)
        self.assertEqual(
            redactions,
            {},
            msg="Got redactions from 'REDACTED' label, but shouldn't have.",
        )

    def test_external_email_banner_no_results(self):
        """Is the 'CAUTION - EXTERNAL EMAIL' banner ignored?"""
        path = root_path / "external_email_banner.pdf"
        redactions = xray.inspect(path)
        self.assertEqual(
            redactions,
            {},
            msg="Got redactions from external email banner, "
            "but shouldn't have.",
        )

    def test_underscore_district_of_no_results(self):
        """Is the '__________ District of __________' form pattern ignored?"""
        path = root_path / "underscore_district_of.pdf"
        redactions = xray.inspect(path)
        self.assertEqual(
            redactions,
            {},
            msg="Got redactions from court form 'District of' field, "
            "but shouldn't have.",
        )

    def test_near_black_redaction_bars(self):
        """Are nearly-unicolor dark redaction bars detected?

        Some PDFs render solid redaction bars with two nearly
        identical dark colors (e.g., differing by 1 per channel).
        These should still be flagged as bad redactions.
        """
        path = root_path / "near_black_redaction_bars.pdf"
        redactions = xray.inspect(path)
        self.assertTrue(
            redactions,
            msg="Expected bad redactions from near-black bars, but got none.",
        )

    def test_unapplied_redact_annotations(self):
        """Do unapplied Redact annotations get flagged as bad redactions?

        When a PDF has Redact annotations that were never applied, the text
        underneath is still visible and extractable. This should be treated
        as a bad redaction.
        """
        path = root_path / "red_rectangle.pdf"
        redactions = xray.inspect(path)
        self.assertTrue(
            redactions,
            msg="Expected bad redactions from unapplied Redact annotations, "
            "but got none.",
        )
        self.assertEqual(
            len(redactions[1]),
            2,
            msg=f"Expected 2 bad redactions from unapplied Redact "
            f"annotations, got {len(redactions.get(1, []))}.",
        )
