"""Run the API server and the ARQ worker in one deployment container."""
import asyncio
import os
import signal
import sys


async def _terminate(processes: list[tuple[str, asyncio.subprocess.Process]]) -> None:
    running = [(name, proc) for name, proc in processes if proc.returncode is None]
    for _, proc in running:
        proc.terminate()

    try:
        await asyncio.wait_for(
            asyncio.gather(*(proc.wait() for _, proc in running)),
            timeout=20,
        )
    except asyncio.TimeoutError:
        for _, proc in running:
            if proc.returncode is None:
                proc.kill()
        await asyncio.gather(*(proc.wait() for _, proc in running))


async def main() -> int:
    port = os.environ.get("PORT", "8000")
    os.environ["_MED_PROCESS_SUPERVISOR"] = "1"
    commands: list[tuple[str, list[str]]] = []

    if os.environ.get("START_ARQ_WORKER", "1") != "0":
        commands.append(
            (
                "ARQ worker",
                [sys.executable, "-m", "arq", "app.workers.arq_settings.WorkerSettings"],
            )
        )

    commands.append(
        (
            "API server",
            [
                sys.executable,
                "-m",
                "uvicorn",
                "app.main:app",
                "--host",
                "0.0.0.0",
                "--port",
                port,
            ],
        )
    )

    processes: list[tuple[str, asyncio.subprocess.Process]] = []
    for name, command in commands:
        print(f"Starting {name}...", flush=True)
        processes.append((name, await asyncio.create_subprocess_exec(*command)))

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    def stop() -> None:
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop)
        except NotImplementedError:
            signal.signal(sig, lambda *_: stop())

    process_tasks = [asyncio.create_task(proc.wait()) for _, proc in processes]
    signal_task = asyncio.create_task(stop_event.wait())
    done, pending = await asyncio.wait(
        [*process_tasks, signal_task],
        return_when=asyncio.FIRST_COMPLETED,
    )

    exit_code = 0
    if signal_task not in done:
        finished = next(task for task in done if task in process_tasks)
        index = process_tasks.index(finished)
        name = processes[index][0]
        exit_code = finished.result()
        print(f"{name} exited with status {exit_code}; stopping remaining processes.", flush=True)

    for task in pending:
        task.cancel()
    await _terminate(processes)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
