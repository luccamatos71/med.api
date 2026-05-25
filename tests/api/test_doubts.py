from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import jwt
from httpx import AsyncClient

from app.core.config import settings
from app.core.database import get_db
from app.main import app


class _ScalarList:
    def __init__(self, values):
        self._values = values

    def all(self):
        return self._values


class _Result:
    def __init__(self, scalar=None, scalars=None, rows=None):
        self._scalar = scalar
        self._scalars = scalars or []
        self._rows = rows or []

    def scalar_one_or_none(self):
        return self._scalar

    def scalar_one(self):
        return self._scalar

    def scalars(self):
        return _ScalarList(self._scalars)

    def all(self):
        return self._rows


class _FakeSession:
    def __init__(self, results):
        self._results = list(results)
        self.added = []

    async def execute(self, _statement):
        return self._results.pop(0)

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        for obj in self.added:
            if getattr(obj, "id", None) is None:
                obj.id = uuid4()

    async def commit(self):
        return None

    async def refresh(self, obj):
        if getattr(obj, "id", None) is None:
            obj.id = uuid4()
        if getattr(obj, "created_at", None) is None:
            obj.created_at = datetime.now(timezone.utc)


def _auth_header(user_id):
    token = jwt.encode({"sub": str(user_id)}, settings.NEXTAUTH_SECRET, algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


async def test_create_doubt_returns_201(client: AsyncClient):
    user_id = uuid4()
    topic_id = uuid4()
    subject_id = uuid4()
    session = _FakeSession(
        [
            _Result(
                scalar=SimpleNamespace(
                    id=topic_id,
                    name="ICC",
                    subject_id=subject_id,
                    user_id=user_id,
                )
            ),
            _Result(scalar="Cardiologia"),
        ]
    )

    async def fake_get_db():
        yield session

    app.dependency_overrides[get_db] = fake_get_db
    try:
        response = await client.post(
            "/api/v1/doubts",
            headers=_auth_header(user_id),
            json={"topic_id": str(topic_id), "question": "Qual a diferença entre BNP e NT-proBNP?"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "pending"
    assert data["topic_name"] == "ICC"
    assert data["subject_name"] == "Cardiologia"


async def test_create_doubt_accepts_material_inside_topic_scope(client: AsyncClient):
    user_id = uuid4()
    topic_id = uuid4()
    subtopic_id = uuid4()
    subject_id = uuid4()
    material_id = uuid4()
    session = _FakeSession(
        [
            _Result(
                scalar=SimpleNamespace(
                    id=topic_id,
                    name="ICC",
                    subject_id=subject_id,
                    user_id=user_id,
                )
            ),
            _Result(scalars=[subtopic_id]),
            _Result(scalar=material_id),
            _Result(scalar="Cardiologia"),
        ]
    )

    async def fake_get_db():
        yield session

    app.dependency_overrides[get_db] = fake_get_db
    try:
        response = await client.post(
            "/api/v1/doubts",
            headers=_auth_header(user_id),
            json={
                "topic_id": str(topic_id),
                "material_id": str(material_id),
                "question": "Fonte correta?",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    assert response.json()["material_id"] == str(material_id)


async def test_create_doubt_rejects_material_outside_topic_scope(client: AsyncClient):
    user_id = uuid4()
    topic_id = uuid4()
    subject_id = uuid4()
    material_id = uuid4()
    session = _FakeSession(
        [
            _Result(
                scalar=SimpleNamespace(
                    id=topic_id,
                    name="ICC",
                    subject_id=subject_id,
                    user_id=user_id,
                )
            ),
            _Result(scalars=[]),
            _Result(scalar=None),
        ]
    )

    async def fake_get_db():
        yield session

    app.dependency_overrides[get_db] = fake_get_db
    try:
        response = await client.post(
            "/api/v1/doubts",
            headers=_auth_header(user_id),
            json={
                "topic_id": str(topic_id),
                "material_id": str(material_id),
                "question": "Fonte indevida?",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json() == {"detail": "Material not found in topic scope"}


async def test_list_doubts_returns_rows(client: AsyncClient):
    user_id = uuid4()
    topic_id = uuid4()
    doubt_id = uuid4()
    session = _FakeSession(
        [
            _Result(
                rows=[
                    (
                        SimpleNamespace(
                            id=doubt_id,
                            user_id=user_id,
                            topic_id=topic_id,
                            material_id=None,
                            question="Pergunta",
                            ai_answer=None,
                            status="pending",
                            resolved_at=None,
                            flashcard_id=None,
                            created_at=datetime.now(timezone.utc),
                        ),
                        "ICC",
                        "Cardiologia",
                    )
                ]
            )
        ]
    )

    async def fake_get_db():
        yield session

    app.dependency_overrides[get_db] = fake_get_db
    try:
        response = await client.get("/api/v1/doubts", headers=_auth_header(user_id))
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["question"] == "Pergunta"
    assert data[0]["topic_name"] == "ICC"


async def test_resolve_doubt_with_flashcard_conversion(client: AsyncClient):
    user_id = uuid4()
    topic_id = uuid4()
    subject_id = uuid4()
    doubt_id = uuid4()
    doubt = SimpleNamespace(
        id=doubt_id,
        user_id=user_id,
        topic_id=topic_id,
        material_id=None,
        question="Q1",
        ai_answer="A1",
        status="pending",
        resolved_at=None,
        flashcard_id=None,
        created_at=datetime.now(timezone.utc),
    )
    session = _FakeSession(
        [
            _Result(scalar=doubt),
            _Result(
                scalar=SimpleNamespace(
                    id=topic_id,
                    name="ICC",
                    subject_id=subject_id,
                    user_id=user_id,
                )
            ),
            _Result(scalar="Cardiologia"),
        ]
    )

    async def fake_get_db():
        yield session

    app.dependency_overrides[get_db] = fake_get_db
    try:
        response = await client.patch(
            f"/api/v1/doubts/{doubt_id}/resolve",
            headers=_auth_header(user_id),
            json={"create_flashcard": True},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "converted_to_flashcard"
    assert data["flashcard_id"] is not None


async def test_doubts_summary_returns_counts(client: AsyncClient):
    user_id = uuid4()
    subject_id = uuid4()
    session = _FakeSession(
        [
            _Result(scalar=3),
            _Result(rows=[(subject_id, "Cardiologia", 2)]),
        ]
    )

    async def fake_get_db():
        yield session

    app.dependency_overrides[get_db] = fake_get_db
    try:
        response = await client.get("/api/v1/doubts/summary", headers=_auth_header(user_id))
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert data["pending_total"] == 3
    assert data["pending_by_subject"][0]["subject_name"] == "Cardiologia"
    assert data["pending_by_subject"][0]["pending_count"] == 2


async def test_get_topic_doubts_endpoint(client: AsyncClient):
    user_id = uuid4()
    topic_id = uuid4()
    subject_id = uuid4()
    doubt_id = uuid4()
    session = _FakeSession(
        [
            _Result(
                scalar=SimpleNamespace(
                    id=topic_id,
                    name="ICC",
                    subject_id=subject_id,
                    user_id=user_id,
                )
            ),
            _Result(scalar="Cardiologia"),
            _Result(
                scalars=[
                    SimpleNamespace(
                        id=doubt_id,
                        user_id=user_id,
                        topic_id=topic_id,
                        material_id=None,
                        question="Pergunta do tópico",
                        ai_answer=None,
                        status="pending",
                        resolved_at=None,
                        flashcard_id=None,
                        created_at=datetime.now(timezone.utc),
                    )
                ]
            ),
        ]
    )

    async def fake_get_db():
        yield session

    app.dependency_overrides[get_db] = fake_get_db
    try:
        response = await client.get(
            f"/api/v1/topics/{topic_id}/doubts",
            headers=_auth_header(user_id),
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["topic_name"] == "ICC"
