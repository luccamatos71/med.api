from app.embedded_worker import should_start_embedded_worker


def test_embedded_worker_starts_on_direct_railway_start(monkeypatch):
    monkeypatch.setenv("RAILWAY_ENVIRONMENT", "production")
    monkeypatch.delenv("_MED_PROCESS_SUPERVISOR", raising=False)
    monkeypatch.delenv("VERCEL", raising=False)
    monkeypatch.delenv("START_ARQ_WORKER", raising=False)
    monkeypatch.delenv("START_EMBEDDED_ARQ_WORKER", raising=False)

    assert should_start_embedded_worker() is True


def test_embedded_worker_skips_supervised_or_serverless_runtime(monkeypatch):
    monkeypatch.setenv("RAILWAY_ENVIRONMENT", "production")
    monkeypatch.setenv("_MED_PROCESS_SUPERVISOR", "1")
    assert should_start_embedded_worker() is False

    monkeypatch.delenv("_MED_PROCESS_SUPERVISOR")
    monkeypatch.setenv("VERCEL", "1")
    assert should_start_embedded_worker() is False


def test_embedded_worker_can_be_disabled(monkeypatch):
    monkeypatch.setenv("RAILWAY_ENVIRONMENT", "production")
    monkeypatch.setenv("START_ARQ_WORKER", "0")

    assert should_start_embedded_worker() is False
