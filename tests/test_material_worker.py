from types import SimpleNamespace
from uuid import uuid4

import fitz

from app.workers import material_worker


def _image_only_pdf_bytes() -> bytes:
    doc = fitz.open()
    doc.new_page()
    payload = doc.tobytes()
    doc.close()
    return payload


class _Result:
    def __init__(self, material=None):
        self.material = material

    def scalar_one_or_none(self):
        return self.material

    def scalar_one(self):
        return self.material


class _FakeSession:
    def __init__(self, results):
        self.results = list(results)
        self.commits = 0

    async def execute(self, _statement):
        return self.results.pop(0)

    async def commit(self):
        self.commits += 1


class _SessionContext:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, *_args):
        return None


async def test_image_only_pdf_becomes_viewable_without_embedding(monkeypatch):
    material_id = uuid4()
    material = SimpleNamespace(
        id=material_id,
        type="pdf",
        file_key="materials/user/id/material.pdf",
        content=None,
        user_id=uuid4(),
        processing_status="pending",
        processing_error=None,
        processed_at=None,
    )
    sessions = iter(
        [
            _FakeSession([_Result(material)]),
            _FakeSession([_Result(), _Result(material)]),
        ]
    )

    monkeypatch.setattr(material_worker, "AsyncSessionLocal", lambda: _SessionContext(next(sessions)))
    monkeypatch.setattr(material_worker, "_download_from_storage", lambda _key: _image_only_pdf_bytes())

    await material_worker.process_material(None, str(material_id))

    assert material.processing_status == "ready"
    assert material.processing_error == "PDF disponivel para leitura, mas sem texto extraivel para o Tutor."
    assert material.processed_at is not None
