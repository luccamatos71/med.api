from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import jwt
from httpx import AsyncClient
from unittest.mock import AsyncMock, patch

from app.ai.rag import _maybe_summarize_history
from app.core.config import settings
from app.core.database import get_db
from app.main import app


class _ScalarList:
    def __init__(self, values):
        self._values = values

    def all(self):
        return self._values


class _Result:
    def __init__(self, scalar=None, scalars=None):
        self._scalar = scalar
        self._scalars = scalars or []

    def scalar_one_or_none(self):
        return self._scalar

    def scalars(self):
        return _ScalarList(self._scalars)


class _FakeSession:
    def __init__(self, results):
        self._results = list(results)
        self.statements = []
        self.added = []
        self.commits = 0

    async def execute(self, statement):
        self.statements.append(statement)
        return self._results.pop(0)

    async def commit(self):
        self.commits += 1

    async def refresh(self, _obj):
        return None

    def add(self, obj):
        self.added.append(obj)


def _auth_header(user_id):
    token = jwt.encode({"sub": str(user_id)}, settings.NEXTAUTH_SECRET, algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


async def test_get_chat_history_returns_owned_topic_messages(client: AsyncClient):
    user_id = uuid4()
    topic_id = uuid4()
    message_id = uuid4()
    now = datetime.now(timezone.utc)
    session = _FakeSession([
        _Result(scalar=SimpleNamespace(id=topic_id, user_id=user_id)),
        _Result(
            scalars=[
                SimpleNamespace(
                    id=message_id,
                    role="assistant",
                    content="Resposta com fonte.",
                    cited_chunks=[
                        {
                            "chunk_id": str(uuid4()),
                            "material_title": "Aula.pdf",
                            "page_number": 3,
                            "snippet": "Trecho citado",
                        }
                    ],
                    tokens_used=42,
                    created_at=now,
                )
            ]
        ),
    ])

    async def fake_get_db():
        yield session

    app.dependency_overrides[get_db] = fake_get_db
    try:
        response = await client.get(
            f"/api/v1/topics/{topic_id}/chat/messages",
            headers=_auth_header(user_id),
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["id"] == str(message_id)
    assert data[0]["role"] == "assistant"
    assert data[0]["content"] == "Resposta com fonte."
    assert data[0]["tokens_used"] == 42
    assert data[0]["cited_chunks"] == [
        {
            "chunk_id": data[0]["cited_chunks"][0]["chunk_id"],
            "material_title": "Aula.pdf",
            "material_id": None,
            "topic_id": None,
            "subject_id": None,
            "page_number": 3,
            "snippet": "Trecho citado",
        }
    ]
    assert data[0]["created_at"]
    assert len(session.statements) == 2


async def test_get_chat_history_returns_404_for_foreign_topic(client: AsyncClient):
    user_id = uuid4()
    topic_id = uuid4()
    session = _FakeSession([_Result(scalar=None)])

    async def fake_get_db():
        yield session

    app.dependency_overrides[get_db] = fake_get_db
    try:
        response = await client.get(
            f"/api/v1/topics/{topic_id}/chat/messages",
            headers=_auth_header(user_id),
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json() == {"detail": "Topic not found"}
    assert len(session.statements) == 1


async def test_chat_stream_returns_503_without_openai_key(client: AsyncClient):
    user_id = uuid4()
    topic_id = uuid4()
    session = _FakeSession([_Result(scalar=SimpleNamespace(id=topic_id, user_id=user_id))])

    async def fake_get_db():
        yield session

    original_key = settings.OPENAI_API_KEY
    settings.OPENAI_API_KEY = ""
    app.dependency_overrides[get_db] = fake_get_db
    try:
        response = await client.post(
            f"/api/v1/topics/{topic_id}/chat/stream",
            headers=_auth_header(user_id),
            json={"question": "O que é ICC?"},
        )
    finally:
        settings.OPENAI_API_KEY = original_key
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json()["detail"] == "OPENAI_API_KEY is not configured"


async def test_chat_stream_returns_sse_events(client: AsyncClient):
    user_id = uuid4()
    topic_id = uuid4()
    session = _FakeSession([_Result(scalar=SimpleNamespace(id=topic_id, user_id=user_id))])

    async def fake_get_db():
        yield session

    async def fake_stream_chat(*_args, **_kwargs):
        yield 'data: {"type":"token","content":"Oi"}\n\n'
        yield 'data: {"type":"done","message_id":"abc"}\n\n'

    original_key = settings.OPENAI_API_KEY
    settings.OPENAI_API_KEY = "test-key"
    app.dependency_overrides[get_db] = fake_get_db
    try:
        with patch("app.api.v1.routes.chat.stream_chat", fake_stream_chat):
            response = await client.post(
                f"/api/v1/topics/{topic_id}/chat/stream",
                headers=_auth_header(user_id),
                json={"question": "Oi?"},
            )
    finally:
        settings.OPENAI_API_KEY = original_key
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    text = response.text
    assert '"type":"token"' in text
    assert '"type":"done"' in text


async def test_chat_stream_forwards_active_material_id(client: AsyncClient):
    user_id = uuid4()
    topic_id = uuid4()
    subtopic_id = uuid4()
    active_material_id = uuid4()
    session = _FakeSession(
        [
            _Result(scalar=SimpleNamespace(id=topic_id, user_id=user_id)),
            _Result(scalars=[subtopic_id]),
            _Result(scalar=active_material_id),
        ]
    )

    async def fake_get_db():
        yield session

    captured_kwargs = {}

    async def fake_stream_chat(*_args, **kwargs):
        captured_kwargs.update(kwargs)
        yield 'data: {"type":"done","message_id":"abc"}\n\n'

    original_key = settings.OPENAI_API_KEY
    settings.OPENAI_API_KEY = "test-key"
    app.dependency_overrides[get_db] = fake_get_db
    try:
        with patch("app.api.v1.routes.chat.stream_chat", fake_stream_chat):
            response = await client.post(
                f"/api/v1/topics/{topic_id}/chat/stream",
                headers=_auth_header(user_id),
                json={"question": "Oi?", "active_material_id": str(active_material_id)},
            )
    finally:
        settings.OPENAI_API_KEY = original_key
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert captured_kwargs["active_material_id"] == active_material_id


async def test_chat_stream_rejects_active_material_outside_scope(client: AsyncClient):
    user_id = uuid4()
    topic_id = uuid4()
    subtopic_id = uuid4()
    active_material_id = uuid4()
    session = _FakeSession(
        [
            _Result(scalar=SimpleNamespace(id=topic_id, user_id=user_id)),
            _Result(scalars=[subtopic_id]),
            _Result(scalar=None),
        ]
    )

    async def fake_get_db():
        yield session

    original_key = settings.OPENAI_API_KEY
    settings.OPENAI_API_KEY = "test-key"
    app.dependency_overrides[get_db] = fake_get_db
    try:
        response = await client.post(
            f"/api/v1/topics/{topic_id}/chat/stream",
            headers=_auth_header(user_id),
            json={"question": "Oi?", "active_material_id": str(active_material_id)},
        )
    finally:
        settings.OPENAI_API_KEY = original_key
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json() == {"detail": "Active material not found in topic scope"}


async def test_chat_stream_logs_and_emits_error_event_on_failure(client: AsyncClient, caplog):
    user_id = uuid4()
    topic_id = uuid4()
    session = _FakeSession([_Result(scalar=SimpleNamespace(id=topic_id, user_id=user_id))])

    async def fake_get_db():
        yield session

    async def failing_stream_chat(*_args, **_kwargs):
        raise RuntimeError("boom")
        yield  # pragma: no cover

    original_key = settings.OPENAI_API_KEY
    settings.OPENAI_API_KEY = "test-key"
    app.dependency_overrides[get_db] = fake_get_db
    try:
        with patch("app.api.v1.routes.chat.stream_chat", failing_stream_chat):
            response = await client.post(
                f"/api/v1/topics/{topic_id}/chat/stream",
                headers=_auth_header(user_id),
                json={"question": "Oi?"},
            )
    finally:
        settings.OPENAI_API_KEY = original_key
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert '"type": "error"' in response.text
    assert "Chat stream failed" in caplog.text


async def test_long_chat_history_is_compressed_into_system_summary():
    user_id = uuid4()
    topic_id = uuid4()
    messages = [
        SimpleNamespace(id=uuid4(), role="user", content=f"Mensagem {index}")
        for index in range(31)
    ]
    session = _FakeSession([_Result(scalars=messages), _Result()])
    summary_response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="Resumo consolidado."))]
    )
    client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=AsyncMock(return_value=summary_response))
        )
    )

    original_key = settings.OPENAI_API_KEY
    settings.OPENAI_API_KEY = "test-key"
    try:
        with patch("app.ai.rag.AsyncOpenAI", return_value=client):
            await _maybe_summarize_history(session, topic_id, str(user_id))
    finally:
        settings.OPENAI_API_KEY = original_key

    assert len(session.statements) == 2
    assert session.commits == 1
    assert len(session.added) == 1
    assert session.added[0].role == "system"
    assert session.added[0].content == "Resumo consolidado."
