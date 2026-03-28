"""
Inspect a PDF's structure for redaction-relevant features.

Dumps drawings (with fill colors, opacity, item types), text traces,
and annotations for each page.  Useful for understanding *why* x-ray
does or doesn't flag something before diving into the pipeline.

Usage::

    .venv/bin/python tools/inspect-pdf.py <path-to-pdf> [--page N]

Options:
    --page N    Only inspect page N (0-indexed).  Default: all pages.
"""

import argparse
from collections import Counter

import fitz


def inspect_page(page: fitz.Page, page_num: int) -> None:
    drawings = page.get_drawings()
    filled = [d for d in drawings if d.get("fill") is not None]

    print(f"\n{'=' * 60}")
    print(f"Page {page_num}: {len(drawings)} drawings, {len(filled)} filled")
    print(f"{'=' * 60}")

    # --- Fill color summary ---
    colors: Counter[tuple[float, ...]] = Counter()
    for d in filled:
        colors[d["fill"]] += 1
    if colors:
        print(f"\nFill colors ({len(colors)} unique):")
        for color, count in colors.most_common(10):
            print(f"  {color}: {count} drawings")

    # --- Large filled rectangles (potential redactions) ---
    print("\nLarge filled shapes (height>8, width>20):")
    for d in filled:
        if d.get("fill_opacity") != 1:
            continue
        item_types = {item[0] for item in d["items"]}
        has_re = "re" in item_types

        # Check both "re" items and the drawing's bounding rect
        rects = []
        if has_re:
            rects = [
                item[1]
                for item in d["items"]
                if item[0] == "re"
                and item[1].height > 8
                and item[1].width > 20
            ]
        else:
            r = d["rect"]
            if r.height > 8 and r.width > 20:
                rects = [r]

        for r in rects:
            shape = "re" if has_re else "lines+curves"
            print(
                f"  [{shape}] fill={d['fill']}, seqno={d['seqno']}, rect={r}"
            )

    # --- Annotations ---
    annots = list(page.annots() or [])
    if annots:
        print(f"\nAnnotations ({len(annots)}):")
        for a in annots:
            print(f"  type={a.type}, colors={a.colors}, rect={a.rect}")
    else:
        print("\nAnnotations: none")

    # --- Text summary ---
    spans = page.get_texttrace()
    if spans:
        text_colors: Counter[tuple[float, ...]] = Counter()
        for s in spans:
            text_colors[s["color"]] += 1
        print(f"\nText spans: {len(spans)}")
        print(f"Text colors ({len(text_colors)} unique):")
        for color, count in text_colors.most_common(5):
            print(f"  {color}: {count} spans")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Inspect PDF structure for redaction-relevant features"
    )
    parser.add_argument("pdf", help="Path to the PDF file")
    parser.add_argument(
        "--page",
        type=int,
        default=None,
        help="Inspect only this page (0-indexed)",
    )
    args = parser.parse_args()

    doc = fitz.open(args.pdf)
    print(f"File: {args.pdf}")
    print(f"Pages: {len(doc)}")

    pages = [args.page] if args.page is not None else range(len(doc))
    for page_num in pages:
        inspect_page(doc[page_num], page_num)


if __name__ == "__main__":
    main()
