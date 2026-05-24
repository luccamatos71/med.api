"""Embedded ARQ worker lifecycle for single-process platform starts."""
import asyncio
import logging
import os
import sys
from contextlib import suppress

logger = logging.getLogger(__name__)

_worker_task: asyncio.Task[None] | None = None
_worker_process: asyncio.subprocess.Process | None = None
_stop_event: asyncio.Event | None = None


def _env_flag(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "no", "off"}


def should_start_embedded_worker() -> bool:
    """Start a worker when Railway runs uvicorn directly instead of start.sh."""
    if os.environ.get("_MED_PROCESS_SUPERVISOR") == "1":
        return False
    if os.environ.get("VERCEL"):
        return False
    if not _env_flag("START_ARQ_WORKER", True):
        return False

    explicit = os.environ.get("START_EMBEDDED_ARQ_WORKER")
    if explicit is not None:
        return _env_flag("START_EMBEDDED_ARQ_WORKER", False)

    return any(
        os.environ.get(name)
        for name in ("RAILWAY_ENVIRONMENT", "RAILWAY_PROJECT_ID", "RAILWAY_SERVICE_ID")
    )


async def _run_worker_until_stopped(stop_event: asyncio.Event) -> None:
    global _worker_process

    backoff_seconds = 1
    command = [sys.executable, "-m", "arq", "app.workers.arq_settings.WorkerSettings"]

    while not stop_event.is_set():
        logger.warning("Starting embedded ARQ worker")
        _worker_process = await asyncio.create_subprocess_exec(*command)

        wait_task = asyncio.create_task(_worker_process.wait())
        stop_task = asyncio.create_task(stop_event.wait())
        done, pending = await asyncio.wait(
            {wait_task, stop_task},
            return_when=asyncio.FIRST_COMPLETED,
        )

        for task in pending:
            task.cancel()

        if stop_task in done:
            break

        exit_code = wait_task.result()
        logger.error("Embedded ARQ worker exited with status %s", exit_code)
        if stop_event.is_set():
            break

        await asyncio.sleep(backoff_seconds)
        backoff_seconds = min(backoff_seconds * 2, 30)


async def start_embedded_worker() -> None:
    global _stop_event, _worker_task

    if _worker_task or not should_start_embedded_worker():
        return

    _stop_event = asyncio.Event()
    _worker_task = asyncio.create_task(_run_worker_until_stopped(_stop_event))


async def stop_embedded_worker() -> None:
    global _stop_event, _worker_process, _worker_task

    if _stop_event:
        _stop_event.set()

    if _worker_process and _worker_process.returncode is None:
        _worker_process.terminate()
        try:
            await asyncio.wait_for(_worker_process.wait(), timeout=20)
        except asyncio.TimeoutError:
            _worker_process.kill()
            await _worker_process.wait()

    if _worker_task:
        with suppress(asyncio.CancelledError):
            await _worker_task

    _worker_process = None
    _worker_task = None
    _stop_event = None
