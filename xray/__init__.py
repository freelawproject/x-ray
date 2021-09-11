"""
Find bad redactions.
"""

from pathlib import Path
from typing import Dict, List, Union

import fitz

from .custom_types import RedactionType
from .pdf_utils import get_bad_redactions


def inspect(file_path: Union[str, Path]) -> Dict[int, List[RedactionType]]:
    """
    Inspect a file for bad redactions and return a Dict with their info

    :file_path: The path to a PDF
    :return: Either a dict with the bad redaction information or None if no bad
    redactions are found.
    """
    pdf = fitz.open(file_path)
    bad_redactions = {}
    for page_number, page in enumerate(pdf, start=1):
        bad_redactions[page_number] = get_bad_redactions(page)
    pdf.close()

    return bad_redactions
