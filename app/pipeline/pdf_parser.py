"""PDF text extraction using PyMuPDF (fitz)."""
from typing import Optional

import fitz  # PyMuPDF


def parse_pdf(file_bytes: bytes) -> list[dict]:
    """Extract text from a PDF file page by page.

    Args:
        file_bytes: Raw PDF bytes.

    Returns:
        List of dicts with keys: text, page_number, section.

    Raises:
        ValueError: If the PDF contains no extractable text (likely a scanned image).
    """
    doc = fitz.open(stream=file_bytes, filetype="pdf")
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

    doc.close()

    total_text = "".join(p["text"].strip() for p in pages)
    if not total_text:
        raise ValueError(
            "PDF parece ser uma imagem. Tenta colar o texto manualmente?"
        )

    return pages
