"""
Extract specific pages from a PDF with compression.

Useful for creating test assets from large PDFs that would exceed
the 5MB pre-commit file size limit.

Usage::

    .venv/bin/python tools/trim-pdf.py input.pdf output.pdf --pages 0,5,19
    .venv/bin/python tools/trim-pdf.py input.pdf output.pdf --pages 0-4

Pages are 0-indexed.  Supports comma-separated page numbers and
ranges (e.g., ``0,5,10-15``).
"""

import argparse
import os
import sys

import fitz


def parse_pages(spec: str) -> list[int]:
    """Parse a page spec like '0,5,10-15' into a list of ints."""
    pages: list[int] = []
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            start, end = part.split("-", 1)
            pages.extend(range(int(start), int(end) + 1))
        else:
            pages.append(int(part))
    return pages


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract pages from a PDF with compression"
    )
    parser.add_argument("input", help="Path to the input PDF")
    parser.add_argument("output", help="Path for the output PDF")
    parser.add_argument(
        "--pages",
        required=True,
        help="Pages to extract (0-indexed). "
        "Comma-separated and/or ranges: 0,5,10-15",
    )
    args = parser.parse_args()

    pages = parse_pages(args.pages)
    doc = fitz.open(args.input)

    for p in pages:
        if p < 0 or p >= len(doc):
            print(f"Error: page {p} out of range (0-{len(doc) - 1})")
            sys.exit(1)

    new_doc = fitz.open()
    for p in pages:
        new_doc.insert_pdf(doc, from_page=p, to_page=p)

    new_doc.save(args.output, garbage=4, deflate=True, clean=True)
    new_doc.close()
    doc.close()

    size = os.path.getsize(args.output)
    print(f"Saved {len(pages)} pages to {args.output} ({size / 1024:.0f}KB)")


if __name__ == "__main__":
    main()
