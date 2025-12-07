"""
Find bad redactions.
"""

import sys
from pathlib import Path

import requests
from fitz import Document

from .custom_types import PdfRedactionsDict
from .pdf_utils import get_bad_redactions
from .text_utils import check_if_all_dates


def inspect(file: str | bytes | Path) -> PdfRedactionsDict:
    """
    Inspect a file for bad redactions and return a Dict with their info

    :file: The PDF to process, as bytes if you have the file in memory (useful
    if it's coming from the network), as a unicode string if you know the
    path to the file on your local disk, or as a pathlib.Path object.
    :return: A dict with the bad redaction information. If no bad redactions
    are found, returns an empty dict.
    """
    if isinstance(file, bytes):
        pdf = Document(stream=file, filetype="pdf")
    elif isinstance(file, str) and file.startswith("https://"):
        r = requests.get(file, timeout=10)
        r.raise_for_status()
        pdf = Document(stream=r.content, filetype="pdf")
    else:
        # str filepath or Pathlib Path
        pdf = Document(file)

    bad_redactions = {}
    for page_number, page in enumerate(pdf, start=1):
        redactions = get_bad_redactions(page)
        if redactions:
            bad_redactions[page_number] = redactions
    pdf.close()
    bad_redactions = check_if_all_dates(bad_redactions)

    return bad_redactions


def cli(args=None):
    """Process command line arguments."""
    if not args:
        args = sys.argv[1:]
    file = args[0]
    print(inspect(file))
