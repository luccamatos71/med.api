import json
from types import SimpleNamespace

import pytest

from app.services import summary_generator
from app.schemas.summary import SummaryContent

VALID_SUMMARY = {
    "title": "Introdução à Farmacologia",
    "tldr": "Visão geral dos conceitos básicos da farmacologia.",
    "key_points": ["Farmacocinética", "Farmacodinâmica"],
    "sections": [{"heading": "Conceitos", "bullets": ["absorção", "distribuição"]}],
    "glossary": [{"term": "Biodisponibilidade", "definition": "fração que atinge a circulação"}],
    "clinical_pearls": ["IV = 100% de biodisponibilidade"],
    "mindmap_markdown": "# Farmacologia\n## Cinética\n- absorção",
}


def _client_returning(payload: str, capture: dict):
    class _Completions:
        async def create(self, **kwargs):
            capture["messages"] = kwargs["messages"]
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=payload))]
            )

    class _Client:
        def __init__(self):
            self.chat = SimpleNamespace(completions=_Completions())

    return _Client()


@pytest.mark.asyncio
async def test_generate_summary_parses_structured_json(monkeypatch):
    capture = {}
    monkeypatch.setattr(summary_generator.settings, "OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(
        summary_generator, "AsyncOpenAI", lambda **_kw: _client_returning(json.dumps(VALID_SUMMARY), capture)
    )

    chunks = [{"content": "Farmacologia geral...", "metadata": {"page_number": 1}}]
    result = await summary_generator.generate_summary_from_chunks(chunks)

    assert isinstance(result, SummaryContent)
    assert result.title == "Introdução à Farmacologia"
    assert "Farmacocinética" in result.key_points
    assert result.mindmap_markdown.startswith("# Farmacologia")
    # material context was passed to the model
    assert any("Material:" in m["content"] for m in capture["messages"])


@pytest.mark.asyncio
async def test_generate_summary_requires_chunks(monkeypatch):
    monkeypatch.setattr(summary_generator.settings, "OPENAI_API_KEY", "test-key")
    with pytest.raises(RuntimeError):
        await summary_generator.generate_summary_from_chunks([])
