import json
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.ai import assistant


class _FakeStream:
    def __init__(self, chunks):
        self._chunks = chunks

    def __aiter__(self):
        self._iter = iter(self._chunks)
        return self

    async def __anext__(self):
        try:
            return next(self._iter)
        except StopIteration as exc:  # pragma: no cover
            raise StopAsyncIteration from exc


def _fake_client(captured):
    class _FakeCompletions:
        async def create(self, **kwargs):
            captured["messages"] = kwargs["messages"]
            chunks = [
                SimpleNamespace(
                    choices=[SimpleNamespace(delta=SimpleNamespace(content="**Resposta** natural."))],
                    usage=None,
                )
            ]
            return _FakeStream(chunks)

    class _FakeClient:
        def __init__(self):
            self.chat = SimpleNamespace(completions=_FakeCompletions())

    return _FakeClient()


def _conversation():
    return SimpleNamespace(id=uuid4(), title="Existente", topic_id=None, material_id=None)


def _parse_events(events):
    return [json.loads(e[len("data: ") :]) for e in events if e.startswith("data: ")]


@pytest.mark.asyncio
async def test_assistant_answers_generally_without_sources(monkeypatch):
    user_id = str(uuid4())
    captured = {}

    async def fake_embed_text(_text):
        return [0.1]

    async def fake_search(*_args, **_kwargs):
        return []

    async def fake_history(*_args, **_kwargs):
        return []

    async def fake_save(*_args, **kwargs):
        captured["cited_chunks"] = kwargs["cited_chunks"]
        captured["answer"] = kwargs["answer"]
        return SimpleNamespace(id=uuid4())

    async def fake_title(*_args, **_kwargs):
        return None

    monkeypatch.setattr(assistant, "embed_text", fake_embed_text)
    monkeypatch.setattr(assistant, "_search_chunks", fake_search)
    monkeypatch.setattr(assistant, "_conversation_history", fake_history)
    monkeypatch.setattr(assistant, "_save_messages", fake_save)
    monkeypatch.setattr(assistant, "_maybe_set_title", fake_title)
    monkeypatch.setattr(assistant, "AsyncOpenAI", lambda **_kwargs: _fake_client(captured))
    monkeypatch.setattr(assistant.settings, "OPENAI_API_KEY", "test-key")

    events = _parse_events(
        [
            event
            async for event in assistant.stream_assistant(
                SimpleNamespace(),
                conversation=_conversation(),
                user_id=user_id,
                question="O que é hipertensão?",
            )
        ]
    )

    source_event = next(e for e in events if e["type"] == "source")
    assert source_event["chunks"] == []
    assert captured["cited_chunks"] == []
    assert "**Resposta** natural." in captured["answer"]
    # No chunks => no retrieved-materials context block is injected.
    assert not any("Trechos dos materiais da estudante:" in m["content"] for m in captured["messages"])


@pytest.mark.asyncio
async def test_assistant_grounds_in_materials_and_emits_real_source(monkeypatch):
    user_id = str(uuid4())
    material_id = uuid4()
    topic_id = uuid4()
    subject_id = uuid4()
    chunk_id = uuid4()
    captured = {}

    async def fake_embed_text(_text):
        return [0.1]

    async def fake_search(*_args, **_kwargs):
        return [
            {
                "id": chunk_id,
                "content": "A pressão arterial sistêmica...",
                "metadata": {"page_number": 7},
                "material_title": "Cardio.pdf",
                "material_id": material_id,
                "topic_id": topic_id,
                "subject_id": subject_id,
            }
        ]

    async def fake_history(*_args, **_kwargs):
        return []

    async def fake_save(*_args, **kwargs):
        captured["cited_chunks"] = kwargs["cited_chunks"]
        return SimpleNamespace(id=uuid4())

    async def fake_title(*_args, **_kwargs):
        return None

    monkeypatch.setattr(assistant, "embed_text", fake_embed_text)
    monkeypatch.setattr(assistant, "_search_chunks", fake_search)
    monkeypatch.setattr(assistant, "_conversation_history", fake_history)
    monkeypatch.setattr(assistant, "_save_messages", fake_save)
    monkeypatch.setattr(assistant, "_maybe_set_title", fake_title)
    monkeypatch.setattr(assistant, "AsyncOpenAI", lambda **_kwargs: _fake_client(captured))
    monkeypatch.setattr(assistant.settings, "OPENAI_API_KEY", "test-key")

    events = _parse_events(
        [
            event
            async for event in assistant.stream_assistant(
                SimpleNamespace(),
                conversation=_conversation(),
                user_id=user_id,
                question="Explica pressão arterial",
            )
        ]
    )

    source_event = next(e for e in events if e["type"] == "source")
    assert len(source_event["chunks"]) == 1
    cited = source_event["chunks"][0]
    assert cited["material_id"] == str(material_id)
    assert cited["topic_id"] == str(topic_id)
    assert cited["subject_id"] == str(subject_id)
    assert cited["page_number"] == 7
    assert any("Trechos dos materiais da estudante:" in m["content"] for m in captured["messages"])
