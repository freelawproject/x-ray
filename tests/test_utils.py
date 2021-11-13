"""
X-Ray Tests
"""
import os
from pathlib import Path
from typing import Tuple
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

root_path = Path(__file__).resolve().parent / "assets"


class RectTest(TestCase):
    """Do our rectangle-finding utilities work properly?"""

    def test_we_find_rectangles_when_we_should(self):
        paths = (
            root_path / "rectangles_yes.pdf",
            root_path / "rectangles_yes_2.pdf",
        )
        for path in paths:
            with fitz.open(path) as pdf:
                page = pdf[0]
                self.assertTrue(get_good_rectangles(page))

    def test_we_do_not_find_rectangles_when_we_should_not(self):
        path = root_path / "rectangles_no.pdf"
        with fitz.open(path) as pdf:
            page = pdf[0]
            self.assertFalse(get_good_rectangles(page))


def rectangle_factory(
    bbox: Tuple[float, ...], seqno: int, fill: float
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
        self.assertEqual(len(bad_redactions), 3)

    def test_finding_bad_redactions_in_a_file(self):
        redactions = xray.inspect(self.path)
        self.assertTrue(len(redactions[1]) == 3)

    def test_empty_pages_no_results(self):
        paths = ("no_bad_redactions.1.1.pdf",)
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
