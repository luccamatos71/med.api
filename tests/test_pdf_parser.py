import fitz
import pytest

from app.pipeline.pdf_parser import PdfHasNoExtractableTextError, parse_pdf, validate_pdf


def _pdf_bytes(text: str | None) -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    if text:
        page.insert_text((72, 72), text)
    payload = doc.tobytes()
    doc.close()
    return payload


def test_validate_pdf_rejects_non_pdf_payload():
    with pytest.raises(ValueError, match="PDF valido"):
        validate_pdf(b"not a pdf")


def test_parse_pdf_extracts_text_pdf():
    pages = parse_pdf(_pdf_bytes("Texto de aula"))

    assert pages[0]["page_number"] == 1
    assert "Texto de aula" in pages[0]["text"]


def test_parse_pdf_allows_storage_but_not_grounding_for_image_only_pdf():
    payload = _pdf_bytes(None)

    validate_pdf(payload)
    with pytest.raises(PdfHasNoExtractableTextError, match="disponivel para leitura"):
        parse_pdf(payload)
