"""
Find bad redactions.
"""

import json
import sys
from pathlib import Path

import httpx2

from ._pymupdf import open_document
from .custom_types import PdfRedactionsDict as PdfRedactionsDict
from .pdf_utils import get_bad_redactions
from .text_utils import check_if_all_dates


async def inspect(file: str | bytes | Path) -> PdfRedactionsDict:
    """
    Inspect a file for bad redactions and return a Dict with their info

    URL downloads are asynchronous; PDF analysis runs synchronously.

    :file: The PDF to process, as bytes if you have the file in memory (useful
    if it's coming from the network), as a unicode string if you know the
    path to the file on your local disk, or as a pathlib.Path object.
    :return: A dict with the bad redaction information. If no bad redactions
    are found, returns an empty dict.
    """
    if isinstance(file, str) and file.startswith("https://"):
        async with httpx2.AsyncClient(
            http2=True, follow_redirects=True, timeout=10
        ) as client:
            response = await client.get(file)
            response.raise_for_status()
            file = response.content

    if isinstance(file, bytes):
        pdf = open_document(stream=file, filetype="pdf")
    else:
        # str filepath or Pathlib Path
        pdf = open_document(file)

    with pdf:
        bad_redactions: PdfRedactionsDict = {}
        for page_index in range(len(pdf)):
            page = pdf[page_index]
            redactions = get_bad_redactions(page)
            if redactions:
                bad_redactions[page_index + 1] = redactions

    return check_if_all_dates(bad_redactions)


async def cli(args: list[str] | None = None) -> None:
    """Process command line arguments."""
    if not args:
        args = sys.argv[1:]
    file = args[0]
    print(json.dumps(await inspect(file), indent=2))
