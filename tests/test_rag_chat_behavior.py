from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.ai import rag


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


@pytest.mark.asyncio
async def test_stream_chat_falls_back_with_deterministic_message_when_no_chunks_and_no_selected_text(
    monkeypatch,
):
    topic_id = uuid4()
    user_id = str(uuid4())

    async def fake_embed_text(_text):
        return [0.1]

    async def fake_topic_material_ids(*_args, **_kwargs):
        return [uuid4()]

    async def fake_search_chunks(*_args, **_kwargs):
        return []

    async def fake_recent_history(*_args, **_kwargs):
        return []

    captured = {}

    async def fake_save_messages(*_args, **kwargs):
        captured["cited_chunks"] = kwargs["cited_chunks"]
        captured["answer"] = kwargs["answer"]
        return SimpleNamespace(id=uuid4())

    async def fake_maybe_summarize(*_args, **_kwargs):
        return None

    class _FakeCompletions:
        async def create(self, **kwargs):
            captured["messages"] = kwargs["messages"]
            chunks = [
                SimpleNamespace(
                    choices=[SimpleNamespace(delta=SimpleNamespace(content="Pensa assim: explicação geral."))],
                    usage=None,
                )
            ]
            return _FakeStream(chunks)

    class _FakeClient:
        def __init__(self):
            self.chat = SimpleNamespace(completions=_FakeCompletions())

    monkeypatch.setattr(rag, "embed_text", fake_embed_text)
    monkeypatch.setattr(rag, "_topic_material_ids", fake_topic_material_ids)
    monkeypatch.setattr(rag, "_search_chunks", fake_search_chunks)
    monkeypatch.setattr(rag, "_recent_history", fake_recent_history)
    monkeypatch.setattr(rag, "_save_messages", fake_save_messages)
    monkeypatch.setattr(rag, "_maybe_summarize_history", fake_maybe_summarize)
    monkeypatch.setattr(rag, "AsyncOpenAI", lambda **_kwargs: _FakeClient())
    monkeypatch.setattr(rag.settings, "OPENAI_API_KEY", "test-key")

    events = [
        event
        async for event in rag.stream_chat(
            SimpleNamespace(),
            topic_id=topic_id,
            user_id=user_id,
            question="Pergunta",
            selected_text=None,
        )
    ]

    assert "Não encontrei isso diretamente nos materiais deste tópico" in events[0]
    assert "Pensa assim: explicação geral." in events[1]
    source_event = next(event for event in events if '"type": "source"' in event)
    assert '"chunks": []' in source_event
    assert captured["cited_chunks"] == []
    assert captured["answer"].startswith("Não encontrei isso diretamente")
    assert captured["answer"].endswith("Pensa assim: explicação geral.")
    assert any("Nenhum trecho relevante foi recuperado" in message["content"] for message in captured["messages"])


@pytest.mark.asyncio
async def test_stream_chat_accepts_single_chunk_and_emits_real_source(monkeypatch):
    topic_id = uuid4()
    user_id = str(uuid4())
    chunk_id = uuid4()
    material_id = uuid4()

    async def fake_embed_text(_text):
        return [0.2]

    async def fake_topic_material_ids(*_args, **_kwargs):
        return [material_id]

    async def fake_search_chunks(*_args, **_kwargs):
        return [
            {
                "id": chunk_id,
                "content": "Conteúdo confiável de um único chunk.",
                "metadata": {"page_number": 7},
                "material_title": "Resumo",
                "material_id": material_id,
                "topic_id": topic_id,
                "similarity": 0.88,
            }
        ]

    async def fake_recent_history(*_args, **_kwargs):
        return []

    async def fake_save_messages(*_args, **_kwargs):
        return SimpleNamespace(id=uuid4())

    async def fake_maybe_summarize(*_args, **_kwargs):
        return None

    class _FakeCompletions:
        async def create(self, **_kwargs):
            chunks = [
                SimpleNamespace(
                    choices=[SimpleNamespace(delta=SimpleNamespace(content="Resposta"))],
                    usage=None,
                )
            ]
            return _FakeStream(chunks)

    class _FakeClient:
        def __init__(self):
            self.chat = SimpleNamespace(completions=_FakeCompletions())

    monkeypatch.setattr(rag, "embed_text", fake_embed_text)
    monkeypatch.setattr(rag, "_topic_material_ids", fake_topic_material_ids)
    monkeypatch.setattr(rag, "_search_chunks", fake_search_chunks)
    monkeypatch.setattr(rag, "_recent_history", fake_recent_history)
    monkeypatch.setattr(rag, "_save_messages", fake_save_messages)
    monkeypatch.setattr(rag, "_maybe_summarize_history", fake_maybe_summarize)
    monkeypatch.setattr(rag, "AsyncOpenAI", lambda **_kwargs: _FakeClient())
    monkeypatch.setattr(rag.settings, "OPENAI_API_KEY", "test-key")

    events = [
        event
        async for event in rag.stream_chat(
            SimpleNamespace(),
            topic_id=topic_id,
            user_id=user_id,
            question="Pergunta",
        )
    ]

    assert any('"type": "source"' in event for event in events)
    source_event = next(event for event in events if '"type": "source"' in event)
    assert str(chunk_id) in source_event
    assert '"page_number": 7' in source_event


@pytest.mark.asyncio
async def test_stream_chat_selected_text_runs_without_chunks_and_keeps_empty_sources(monkeypatch):
    topic_id = uuid4()
    user_id = str(uuid4())

    async def fake_embed_text(_text):
        return [0.3]

    async def fake_topic_material_ids(*_args, **_kwargs):
        return [uuid4()]

    async def fake_search_chunks(*_args, **_kwargs):
        return []

    async def fake_recent_history(*_args, **_kwargs):
        return []

    saved = {}

    async def fake_save_messages(*_args, **kwargs):
        saved["cited_chunks"] = kwargs["cited_chunks"]
        return SimpleNamespace(id=uuid4())

    async def fake_maybe_summarize(*_args, **_kwargs):
        return None

    class _FakeCompletions:
        async def create(self, **_kwargs):
            chunks = [
                SimpleNamespace(
                    choices=[SimpleNamespace(delta=SimpleNamespace(content="Explicação geral"))],
                    usage=None,
                )
            ]
            return _FakeStream(chunks)

    class _FakeClient:
        def __init__(self):
            self.chat = SimpleNamespace(completions=_FakeCompletions())

    monkeypatch.setattr(rag, "embed_text", fake_embed_text)
    monkeypatch.setattr(rag, "_topic_material_ids", fake_topic_material_ids)
    monkeypatch.setattr(rag, "_search_chunks", fake_search_chunks)
    monkeypatch.setattr(rag, "_recent_history", fake_recent_history)
    monkeypatch.setattr(rag, "_save_messages", fake_save_messages)
    monkeypatch.setattr(rag, "_maybe_summarize_history", fake_maybe_summarize)
    monkeypatch.setattr(rag, "AsyncOpenAI", lambda **_kwargs: _FakeClient())
    monkeypatch.setattr(rag.settings, "OPENAI_API_KEY", "test-key")

    events = [
        event
        async for event in rag.stream_chat(
            SimpleNamespace(),
            topic_id=topic_id,
            user_id=user_id,
            question="Pergunta",
            selected_text="trecho importante",
        )
    ]

    source_event = next(event for event in events if '"type": "source"' in event)
    assert '"chunks": []' in source_event
    assert saved["cited_chunks"] == []


@pytest.mark.asyncio
async def test_stream_chat_passes_active_material_hint_to_retrieval(monkeypatch):
    topic_id = uuid4()
    user_id = str(uuid4())
    active_material_id = uuid4()
    captured = {}

    async def fake_embed_text(_text):
        return [0.5]

    async def fake_topic_material_ids(*_args, **_kwargs):
        return [uuid4()]

    async def fake_search_chunks(*_args, **kwargs):
        captured["active_material_id"] = kwargs.get("active_material_id")
        return []

    async def fake_save_messages(*_args, **_kwargs):
        return SimpleNamespace(id=uuid4())

    async def fake_recent_history(*_args, **_kwargs):
        return []

    async def fake_maybe_summarize(*_args, **_kwargs):
        return None

    class _FakeCompletions:
        async def create(self, **_kwargs):
            chunks = [
                SimpleNamespace(
                    choices=[SimpleNamespace(delta=SimpleNamespace(content="Explicação geral"))],
                    usage=None,
                )
            ]
            return _FakeStream(chunks)

    class _FakeClient:
        def __init__(self):
            self.chat = SimpleNamespace(completions=_FakeCompletions())

    monkeypatch.setattr(rag, "embed_text", fake_embed_text)
    monkeypatch.setattr(rag, "_topic_material_ids", fake_topic_material_ids)
    monkeypatch.setattr(rag, "_search_chunks", fake_search_chunks)
    monkeypatch.setattr(rag, "_recent_history", fake_recent_history)
    monkeypatch.setattr(rag, "_save_messages", fake_save_messages)
    monkeypatch.setattr(rag, "_maybe_summarize_history", fake_maybe_summarize)
    monkeypatch.setattr(rag, "AsyncOpenAI", lambda **_kwargs: _FakeClient())
    monkeypatch.setattr(rag.settings, "OPENAI_API_KEY", "test-key")

    async for _event in rag.stream_chat(
        SimpleNamespace(),
        topic_id=topic_id,
        user_id=user_id,
        question="Pergunta",
        active_material_id=active_material_id,
    ):
        pass

    assert captured["active_material_id"] == active_material_id


@pytest.mark.asyncio
async def test_search_chunks_orders_active_material_before_general_relevance():
    active_material_id = uuid4()
    captured = {}

    class _Result:
        def all(self):
            return []

    class _Session:
        async def execute(self, statement):
            captured["statement"] = str(statement)
            return _Result()

    await rag._search_chunks(
        _Session(),
        [0.1] * 1536,
        [active_material_id, uuid4()],
        str(uuid4()),
        active_material_id=active_material_id,
    )

    statement = captured["statement"]
    assert "active_material_priority DESC" in statement
    assert statement.index("active_material_priority DESC") < statement.index("relevance DESC")
