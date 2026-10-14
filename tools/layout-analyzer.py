"""
Utility
--------
Read a document and create a PDF showing the original page layout.
Useful mainly for PDFs where /CropBox is not equal to /Mediabox and / or
when image and text locations should be shown.

The output is a PDF with pages having input /MediaBox dimensions.
All text in the output is repositioned with respect to the /CropBox location
in the input. Text is shown surrounded by its text block rectangle. Images are
not displayed, but their locations are indicated by empty rectangles with
some meta information.
"""

import sys
import time
from collections.abc import Callable
from typing import Literal, Protocol

import pymupdf as fitz

from xray._pymupdf import BBox, open_document

TextBlock = tuple[float, float, float, float, str, int, int]
make_rect: Callable[[BBox], fitz.Rect] = fitz.Rect


class _SaveDocument(Protocol):
    def __call__(
        self, filename: str, *, garbage: int, deflate: bool, clean: bool
    ) -> None: ...


print(fitz.__doc__)
t0 = time.time()
doc1 = open_document(sys.argv[1])
doc2 = open_document()
red = (1, 0, 0)
blue = (0, 0, 1)
green = (0, 1, 0)
gray = (0.9, 0.9, 0.9)

for page_index in range(len(doc1)):
    page1 = doc1[page_index]
    get_blocks: Callable[[Literal["blocks"]], list[TextBlock]] = page1.get_text
    blks = get_blocks("blocks")
    # create new page in output with /MediaBox dimensions
    page_size: fitz.Point = page1.mediabox_size
    page2 = doc2.new_page(-1, width=page_size.x, height=page_size.y)
    # the text font we use
    insert_font: Callable[[str], int] = page2.insert_font
    insert_font("Helvetica")
    new_shape: Callable[[], fitz.Shape] = page2.new_shape
    img = new_shape()  # prepare /Contents object

    # calculate /CropBox & displacement
    position: fitz.Point = page1.cropbox_position
    disp = make_rect((position.x, position.y, position.x, position.y))
    page_rect: fitz.Rect = page1.rect
    croprect: fitz.Rect = page_rect + disp

    # draw original /CropBox rectangle
    img.draw_rect(croprect)
    img.finish(color=gray, fill=gray)

    for b in blks:  # loop through the blocks
        # Add displacement of original /CropBox.
        bbox: BBox = b[:4]
        r: fitz.Rect = make_rect(bbox) + disp
        img.draw_rect(r)  # surround block rectangle

        if b[-1] == 1:  # if image block ...
            color = red
            a = fitz.TEXT_ALIGN_CENTER
        else:  # if text block
            color = blue
            a = fitz.TEXT_ALIGN_LEFT

        img.finish(width=0.3, color=color)

        is_empty: bool = r.is_empty
        page_number: int = page1.number
        if is_empty:  # do not rely on meaningful rects
            print(
                "skipping text of empty rect at (%g, %g) on page %i"  # noqa: UP031
                % (r.x0, r.y0, page_number)
            )
        else:
            # insert text of the block using a small, indicative fontsize
            img.insert_textbox(
                r,
                b[4],
                fontname="/Helvetica",
                fontsize=8,
                color=color,
                align=a,
            )

    img.commit()  # store /Contents of out page

# save output file
save: _SaveDocument = doc2.save
document_name: str = doc1.name
save(f"layout-{document_name}", garbage=4, deflate=True, clean=True)
t1 = time.time()
print(f"total time: {t1 - t0:g} sec")
