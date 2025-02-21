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
from xray.pdf_utils import (
    get_bad_redactions,
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
            chars = get_intersecting_chars(page, get_good_rectangles(page))
        self.assertEqual(len(chars), 64)

    def test_cross_hatches_are_ok(self):
        path = root_path / "bad_cross_hatched_redactions.pdf"
        with fitz.open(path) as pdf:
            page = pdf[0]
            chars = get_intersecting_chars(page, get_good_rectangles(page))
        self.assertEqual(len(chars), 639)

    def test_ignoring_partial_occlusions(self):
        path = root_path / "partial_intersections_ok.pdf"
        with fitz.open(path) as pdf:
            page = pdf[0]
            chars = get_intersecting_chars(page, get_good_rectangles(page))
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
