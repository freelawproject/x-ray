"""
Find bad redactions.
"""

from pathlib import Path
from typing import Union

import fitz

from .custom_types import PdfRedactionsDict
from .pdf_utils import get_bad_redactions


def inspect(file_path: Union[str, Path]) -> PdfRedactionsDict:
    """
    Inspect a file for bad redactions and return a Dict with their info

    :file_path: The PDF to process
    :return: A dict with the bad redaction information. If no bad redactions
    are found, returns an empty dict.
    """
    pdf = fitz.open(file_path)
    bad_redactions = {}
    for page_number, page in enumerate(pdf, start=1):
        redactions = get_bad_redactions(page)
        if redactions:
            bad_redactions[page_number] = redactions
    pdf.close()

    return bad_redactions
