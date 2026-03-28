"""
Quick-inspect a PDF with x-ray and show what it detects.

Usage::

    .venv/bin/python tools/quick-inspect.py <path-to-pdf>
"""

import sys

import xray


def main() -> None:
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <path-to-pdf>")
        sys.exit(1)

    path = sys.argv[1]
    result = xray.inspect(path)
    if result:
        for page, redactions in result.items():
            for r in redactions:
                print(f"Page {page}: text={r['text']!r}")
        total = sum(len(v) for v in result.values())
        print(f"\nTotal: {total} bad redactions")
    else:
        print("No bad redactions detected.")


if __name__ == "__main__":
    main()
