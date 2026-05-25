from types import SimpleNamespace
from uuid import uuid4

from app.workers import arq_settings


class _ScalarList:
    def __init__(self, values):
        self.values = values

    def all(self):
        return self.values


class _Result:
    def __init__(self, values):
        self.values = values

    def scalars(self):
        return _ScalarList(self.values)


class _FakeSession:
    def __init__(self, pending, processing):
        self.results = [_Result(pending), _Result(processing)]
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


class _Redis:
    def __init__(self):
        self.jobs = []

    async def enqueue_job(self, _name, material_id):
        self.jobs.append(material_id)

    async def aclose(self):
        return None


async def test_stale_processing_material_is_failed_while_pending_is_requeued(monkeypatch):
    pending = SimpleNamespace(id=uuid4(), processing_status="pending", processing_error=None)
    processing = SimpleNamespace(id=uuid4(), processing_status="processing", processing_error=None)
    session = _FakeSession([pending], [processing])
    redis = _Redis()

    monkeypatch.setattr(arq_settings, "AsyncSessionLocal", lambda: _SessionContext(session))

    async def fake_pool(_settings):
        return redis

    monkeypatch.setattr(arq_settings, "create_pool", fake_pool)

    await arq_settings.requeue_stale_materials(None)

    assert redis.jobs == [str(pending.id)]
    assert processing.processing_status == "failed"
    assert "interrompido" in processing.processing_error
    assert session.commits == 1
