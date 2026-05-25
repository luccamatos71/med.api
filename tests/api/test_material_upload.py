from datetime import datetime, timezone
from io import BytesIO
from types import SimpleNamespace
from uuid import uuid4

import fitz
import pytest
from fastapi import HTTPException, UploadFile

from app.api.v1.routes import materials


def _pdf_bytes() -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Texto valido")
    payload = doc.tobytes()
    doc.close()
    return payload


class _FakeSession:
    def __init__(self):
        self.added = []

    def add(self, material):
        material.id = uuid4()
        material.created_at = datetime.now(timezone.utc)
        self.added.append(material)

    async def commit(self):
        return None

    async def refresh(self, _material):
        return None


async def test_pdf_upload_keeps_original_title_and_uses_safe_storage_key(monkeypatch):
    uploaded = {}

    async def fake_verify(*_args):
        return None

    async def fake_upload(payload, key, content_type):
        uploaded.update(payload=payload, key=key, content_type=content_type)

    async def fake_enqueue(_material_id):
        return None

    monkeypatch.setattr(materials, "_verify_topic_ownership", fake_verify)
    monkeypatch.setattr(materials, "upload_file", fake_upload)
    monkeypatch.setattr(materials, "_enqueue_process", fake_enqueue)

    response = await materials.upload_pdf(
        topic_id=uuid4(),
        file=UploadFile(
            filename="Relat\u00f3rio audi\u00eancias e sess\u00e3o.pdf",
            file=BytesIO(_pdf_bytes()),
        ),
        current_user={"user_id": str(uuid4())},
        db=_FakeSession(),
    )

    assert response.title == "Relat\u00f3rio audi\u00eancias e sess\u00e3o.pdf"
    assert uploaded["key"].endswith("/material.pdf")
    assert "Relat" not in uploaded["key"]
    assert uploaded["content_type"] == "application/pdf"


async def test_pdf_upload_rejects_non_pdf_payload_before_storage(monkeypatch):
    async def fake_verify(*_args):
        return None

    async def fail_upload(*_args):
        raise AssertionError("storage must not be called")

    monkeypatch.setattr(materials, "_verify_topic_ownership", fake_verify)
    monkeypatch.setattr(materials, "upload_file", fail_upload)

    with pytest.raises(HTTPException) as exc:
        await materials.upload_pdf(
            topic_id=uuid4(),
            file=UploadFile(filename="texto.pdf", file=BytesIO(b"not a pdf")),
            current_user={"user_id": str(uuid4())},
            db=SimpleNamespace(),
        )

    assert exc.value.status_code == 422
