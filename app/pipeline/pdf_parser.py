"""PDF text extraction using PyMuPDF (fitz)."""
from typing import Optional

import fitz  # PyMuPDF


class PdfHasNoExtractableTextError(ValueError):
    """Raised when a valid PDF is viewable but cannot feed Tutor search."""


def validate_pdf(file_bytes: bytes) -> None:
    """Reject malformed payloads before storing them as PDF materials."""
    try:
        with fitz.open(stream=file_bytes, filetype="pdf") as doc:
            if len(doc) == 0:
                raise ValueError("Arquivo invalido. Envie um PDF valido.")
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("Arquivo invalido. Envie um PDF valido.") from exc


def parse_pdf(file_bytes: bytes) -> list[dict]:
    """Extract text from a PDF file page by page.

    Args:
        file_bytes: Raw PDF bytes.

    Returns:
        List of dicts with keys: text, page_number, section.

    Raises:
        PdfHasNoExtractableTextError: If the PDF is viewable but contains no
            extractable text for Tutor grounding.
    """
    with fitz.open(stream=file_bytes, filetype="pdf") as doc:
        pages: list[dict] = []

        for page_index in range(len(doc)):
            page = doc[page_index]
            text = page.get_text("text")
            pages.append(
                {
                    "text": text,
                    "page_number": page_index + 1,
                    "section": None,
                }
            )

    total_text = "".join(p["text"].strip() for p in pages)
    if not total_text:
        raise PdfHasNoExtractableTextError(
            "PDF disponivel para leitura, mas sem texto extraivel para o Tutor."
        )

    return pages
