"""
Walk the x-ray detection pipeline step by step on a PDF.

Shows what gets kept and dropped at each stage (rectangles, chars,
text filter, pixmap filter) so you can pinpoint where detection
fails.  For pixmap-filtered entries it shows color analysis to help
diagnose unicolor/nearly-unicolor issues.

Usage::

    .venv/bin/python tools/debug-pipeline.py <path-to-pdf> [--page N]

Options:
    --page N    Only debug page N (0-indexed).  Default: all pages.
"""

import argparse
from collections import Counter

import fitz

# Match x-ray's rendering settings
fitz.TOOLS.set_aa_level(0)

from xray.pdf_utils import (  # noqa: E402
    _is_nearly_unicolor,
    filter_redactions_by_text,
    get_content_spans,
    get_good_rectangles,
    get_intersecting_chars,
    get_unapplied_redact_annotations,
    group_chars_by_rect,
)


def analyze_pixmap(page: fitz.Page, redaction: dict) -> dict:
    """Render a redaction's bbox and return color analysis."""
    clip = fitz.Rect(redaction["bbox"])
    pixmap = page.get_pixmap(colorspace=fitz.csRGB, clip=clip)

    samples = pixmap.samples
    n = pixmap.n
    total = pixmap.width * pixmap.height

    colors: Counter[tuple[int, ...]] = Counter()
    for p in range(total):
        offset = p * n
        colors[tuple(samples[offset : offset + n])] += 1

    nearly_uniform, dominant = _is_nearly_unicolor(pixmap)

    return {
        "size": f"{pixmap.width}x{pixmap.height}",
        "is_unicolor": pixmap.is_unicolor,
        "nearly_uniform": nearly_uniform,
        "dominant": dominant,
        "unique_colors": len(colors),
        "top_colors": colors.most_common(5),
        "total_pixels": total,
    }


def debug_page(page: fitz.Page, page_num: int) -> None:
    print(f"\n{'=' * 60}")
    print(f"Page {page_num}")
    print(f"{'=' * 60}")

    # Stage 1: rectangles
    rects = get_good_rectangles(page)
    print(f"\n1. Rectangles: {len(rects)}")

    # Stage 2: intersecting chars
    spans = get_content_spans(page)
    chars = get_intersecting_chars(spans, rects)
    print(f"2. Intersecting chars: {len(chars)}")

    # Stage 3: group by rect
    redactions = group_chars_by_rect(chars, rects)
    non_empty = [r for r in redactions if r["text"].strip()]
    print(
        f"3. Grouped redactions: {len(redactions)} ({len(non_empty)} non-empty)"
    )

    # Stage 4: text filter
    text_filtered = filter_redactions_by_text(redactions)
    print(f"4. After text filter: {len(text_filtered)}")

    # Stage 5: pixmap filter (manual, to show details)
    kept = []
    dropped = []
    for r in text_filtered:
        info = analyze_pixmap(page, r)
        if not info["nearly_uniform"]:
            dropped.append((r, info, "not_uniform"))
        elif info["dominant"] and all(c == 255 for c in info["dominant"]):
            dropped.append((r, info, "white"))
        else:
            kept.append((r, info))

    print(f"5. After pixmap filter: {len(kept)} kept, {len(dropped)} dropped")

    if kept:
        print(f"\n  KEPT ({len(kept)}):")
        for r, info in kept:
            print(
                f"    text={r['text'][:50]!r} "
                f"({info['size']}, {info['unique_colors']} colors, "
                f"dominant={info['dominant']})"
            )

    if dropped:
        print(f"\n  DROPPED ({len(dropped)}):")
        for r, info, reason in dropped:
            print(
                f"    [{reason}] text={r['text'][:50]!r} "
                f"({info['size']}, {info['unique_colors']} colors)"
            )
            for color, count in info["top_colors"][:3]:
                pct = 100 * count / info["total_pixels"]
                print(f"      RGB{color}: {count}px ({pct:.1f}%)")

    # Stage 6: unapplied annotations
    unapplied = get_unapplied_redact_annotations(page)
    unapplied_filtered = filter_redactions_by_text(unapplied)
    if unapplied_filtered:
        print(f"\n6. Unapplied Redact annotations: {len(unapplied_filtered)}")
        for r in unapplied_filtered:
            print(f"    text={r['text'][:50]!r}")

    total = len(kept) + len(unapplied_filtered)
    print(f"\n  TOTAL bad redactions: {total}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Debug x-ray detection pipeline on a PDF"
    )
    parser.add_argument("pdf", help="Path to the PDF file")
    parser.add_argument(
        "--page",
        type=int,
        default=None,
        help="Debug only this page (0-indexed)",
    )
    args = parser.parse_args()

    doc = fitz.open(args.pdf)
    print(f"File: {args.pdf}")
    print(f"Pages: {len(doc)}")

    pages = [args.page] if args.page is not None else range(len(doc))
    for page_num in pages:
        debug_page(doc[page_num], page_num)


if __name__ == "__main__":
    main()
