"""
Auto-start Celery worker + beat inside the FastAPI process.

When AUTOSTART_CELERY=True in .env, the FastAPI lifespan spawns a single
Celery process with the -B flag (embedded beat) so you only need to run
the uvicorn command — no separate Celery terminal required.

The Celery process runs in a subprocess and is terminated on shutdown.
"""
import atexit
import os
import subprocess
import sys
from pathlib import Path

from src.core.config import settings

_celery_proc: subprocess.Popen | None = None


def start_celery() -> None:
    """Start a single Celery worker + beat subprocess (idempotent)."""
    global _celery_proc

    if not settings.AUTOSTART_CELERY:
        return

    if _celery_proc is not None and _celery_proc.poll() is None:
        # Already running
        return

    project_root = Path(__file__).resolve().parent.parent.parent
    # Always invoke Celery via the current Python interpreter with "-m celery".
    # The venv's celery.exe launcher embeds a hardcoded path to the Python used
    # to create the venv; if the project folder is moved/renamed, that path
    # becomes stale and the launcher fails ("Unable to create process").
    # Using sys.executable -m celery is robust against venv relocation.
    celery_cmd = [
        sys.executable, "-m", "celery",
        "-A", "src.core.celery_app", "worker",
        "-l", "info", "-P", "solo",
    ]
    # Embedded beat (-B) is not supported on Windows (Celery raises:
    #   "-B option does not work on Windows. Please run celery beat as a
    #    separate service."). The FastAPI process already runs an in-process
    #   scheduler loop (post_scheduler_loop, every 10s), so beat is not
    #   required for core scheduling here. Run beat separately on Windows
    #   only if periodic Celery tasks are needed.
    if sys.platform != "win32":
        celery_cmd.append("-B")

    env = os.environ.copy()
    env["PYTHONPATH"] = str(project_root)

    print("[celery_runner] Starting Celery worker + beat (single process)...")
    _celery_proc = subprocess.Popen(
        celery_cmd,
        cwd=str(project_root),
        env=env,
        # Inherit the terminal so Celery logs are visible alongside uvicorn.
    )
    atexit.register(stop_celery)
    print(f"[celery_runner] Celery started (PID {_celery_proc.pid})")


def stop_celery() -> None:
    """Terminate the Celery subprocess if running."""
    global _celery_proc
    if _celery_proc is None:
        return
    if _celery_proc.poll() is None:
        print("[celery_runner] Stopping Celery...")
        _celery_proc.terminate()
        try:
            _celery_proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            _celery_proc.kill()
    _celery_proc = None