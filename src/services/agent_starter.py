"""
Auto-start the local agent process when a post is due but no agent is online.

The backend keeps the agent's raw token in the DB (AgentDevice.raw_token).
When the scheduler finds a due post whose user has no connected agent, it
calls `ensure_agent_running(user_id)`, which:

  1. Loads the user's most recent active AgentDevice (with a raw_token).
  2. Spawns the agent process (local_agent/agent.py) with the token and WS
     URL passed via environment variables, so the agent starts
     non-interactively and connects back to this server.
  3. Respects a per-user cooldown so it doesn't spam-spawn processes.

The agent process then connects over WebSocket; the WebSocket handler's
"agent-online" hook dispatches the waiting posts to it.

NOTE: This only works when the backend and the agent run on the same
machine (the backend must be able to launch the agent process). For
multi-host deployments, use a process supervisor / systemd / a remote
launch mechanism instead.
"""
import asyncio
import os
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

from sqlalchemy import select

from src.core.config import settings
from src.core.database import AsyncSessionLocal
from src.core.websocket_manager import registry
from src.models.accounts import AgentDevice
from src.models.agent_profile import UserAgentProfile

# Per-user cooldown tracking: user_id -> last spawn time
_last_spawn: dict[int, datetime] = {}
# Currently spawning set to avoid duplicate concurrent spawns
_spawning: set[int] = set()
# PIDs of agents we auto-started, so we can close them when work is done.
_spawned_pids: dict[int, int] = {}
# Warn once when auto-start is disabled because no agent project is configured.
_agent_start_notice_shown = False

# Base directory for per-user Chrome profiles (matches agent_profile router).
PROFILE_BASE_DIR = os.path.join(
    os.environ.get("LOCALAPPDATA", os.path.expanduser("~")),
    "AutoSocialAI",
)


def _get_default_profile_dir(user_id: int) -> str:
    """Default Chrome user-data-dir for a user when none is set in the DB."""
    return os.path.join(PROFILE_BASE_DIR, f"user_{user_id}")


async def _get_agent_token_for_user(user_id: int) -> str | None:
    """Return the raw agent token for the user's most recent active device."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(AgentDevice)
            .where(AgentDevice.user_id == user_id, AgentDevice.is_active == True)
            .order_by(AgentDevice.id.desc())
        )
        device = result.scalars().first()
        return device.raw_token if device else None


async def _get_agent_profile_for_user(user_id: int) -> tuple[str, str]:
    """Return (user_data_dir, profile_directory) for the user's Chrome profile.

    Uses the DB-stored profile if one is set, otherwise falls back to a
    default per-user profile directory so the agent ALWAYS gets an explicit
    Chrome profile (never the agent's built-in default).
    """
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(UserAgentProfile).where(UserAgentProfile.user_id == user_id)
        )
        profile = result.scalar_one_or_none()
        if profile:
            return profile.user_data_dir, profile.profile_directory
    # No profile row in the DB — use the default per-user directory.
    return _get_default_profile_dir(user_id), "Default"


def _is_nonempty_path(value: str | os.PathLike[str] | None) -> bool:
    if value is None:
        return False
    return str(value).strip() not in {"", "."}


def _candidate_agent_roots() -> list[Path]:
    """Return a list of possible agent project roots to inspect."""
    candidates: list[Path] = []

    env_root = os.getenv("AGENT_PROJECT_ROOT")
    if _is_nonempty_path(env_root):
        candidates.append(Path(env_root))

    config_root = getattr(settings, "AGENT_PROJECT_ROOT", None)
    if _is_nonempty_path(config_root):
        candidates.append(Path(config_root))

    repo_root = Path(__file__).resolve().parents[2]
    candidates.extend(
        [
            repo_root,
            repo_root.parent,
            repo_root.parent.parent,
            Path.home(),
            Path(r"D:\RUNNING_PROJECT"),
        ]
    )

    seen: set[Path] = set()
    ordered: list[Path] = []
    for candidate in candidates:
        normalized = candidate.expanduser().resolve(strict=False)
        if normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)
    return ordered


def _resolve_agent_paths() -> tuple[Path | None, Path | None]:
    """Find an agent script and matching Python interpreter if possible."""
    for root in _candidate_agent_roots():
        # Prefer the new isolated agent package, but keep compatibility with the
        # old root-level path for older setups.
        agent_script = root / "agent" / "local_agent" / "agent.py"
        if not agent_script.exists():
            agent_script = root / "local_agent" / "agent.py"
        if not agent_script.exists():
            agent_script = root / "local_agent" / "agent_stub.py"
        if not agent_script.exists():
            continue

        python_candidates: list[Path] = []

        env_python = os.getenv("AGENT_PYTHON")
        if _is_nonempty_path(env_python):
            python_candidates.append(Path(env_python))

        config_python = getattr(settings, "AGENT_PYTHON", None)
        if _is_nonempty_path(config_python):
            python_candidates.append(Path(config_python))

        python_candidates.extend(
            [
                root / ".venv" / "Scripts" / "python.exe",
                root / ".venv" / "bin" / "python",
                root / "venv" / "Scripts" / "python.exe",
                root / "venv" / "bin" / "python",
            ]
        )

        for python_candidate in python_candidates:
            if python_candidate.exists():
                return agent_script, python_candidate

        return agent_script, None

    return None, None


async def ensure_agent_running(user_id: int) -> bool:
    """Spawn the local agent for this user if not already online and not on cooldown.

    Returns True if a spawn was attempted (or agent already online), False if
    skipped (cooldown / no token / disabled).
    """
    if not settings.AGENT_START_ENABLED:
        return False

    # Already online — nothing to do.
    if registry.is_online(user_id):
        return True

    # Already spawning — avoid duplicate launches.
    if user_id in _spawning:
        return False

    # Cooldown check.
    now = datetime.now(timezone.utc)
    last = _last_spawn.get(user_id)
    if last and (now - last) < timedelta(seconds=settings.AGENT_START_COOLDOWN_SECONDS):
        return False

    # Locate the agent script.
    agent_script, python_exe = _resolve_agent_paths()
    if not agent_script:
        global _agent_start_notice_shown
        if not _agent_start_notice_shown:
            print(
                "[agent-starter] INFO: Auto-start is disabled because no agent project with "
                "local_agent/agent.py was found. Set AGENT_PROJECT_ROOT/AGENT_PYTHON "
                "or enable AGENT_START_ENABLED once the agent project is available."
            )
            _agent_start_notice_shown = True
        return False

    if not python_exe:
        print(
            f"[agent-starter] ERROR: Agent python not found for {agent_script}\n"
            f"[agent-starter]        Set AGENT_PYTHON in .env to the agent's venv python.exe."
        )
        return False

    # Fetch the stored raw token for this user.
    token = await _get_agent_token_for_user(user_id)
    if not token:
        print(f"[agent-starter] WARN: No agent token stored for user {user_id}; cannot auto-start.")
        return False

    _spawning.add(user_id)
    _last_spawn[user_id] = now

    try:
        env = os.environ.copy()
        env[settings.AGENT_TOKEN_ENV] = token
        env[settings.AGENT_WS_URL_ENV] = settings.AGENT_WS_URL
        # Force UTF-8 for the child so emoji prints don't crash on Windows.
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"

        # Pass the user's Chrome profile so the agent uses the right
        # browser profile (each user has their own social media logins).
        # Always set an explicit profile — from the DB if available, else the
        # default per-user directory — so the agent never falls back to its
        # own built-in default.
        user_data_dir, profile_directory = await _get_agent_profile_for_user(user_id)
        env["CHROME_USER_DATA_DIR"] = user_data_dir
        env["CHROME_PROFILE_DIRECTORY"] = profile_directory
        # Also pass the backend base URL + token so a manually-started agent
        # can fetch its profile from /agent-profile/by-token/ as a fallback.
        env["AGENT_API_BASE_URL"] = settings.BASE_URL
        print(
            f"[agent-starter] Using Chrome profile for user {user_id}: "
            f"user_data_dir={user_data_dir}, profile_directory={profile_directory}"
        )

        # Spawn in a new console window so the agent (which uses a browser
        # automation library) has a proper environment. DETACHED_PROCESS
        # causes the browser manager to fail silently.
        creationflags = 0
        if sys.platform == "win32":
            creationflags = 0x00000010  # CREATE_NEW_CONSOLE

        # Log agent output to a file so we can debug auto-start failures.
        from src.core.config import BASE_DIR
        log_dir = BASE_DIR / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / f"agent_user_{user_id}.log"
        # Truncate the log on each new spawn so we see only the current run.
        log_file = open(log_path, "w", encoding="utf-8")

        import subprocess
        proc = subprocess.Popen(
            [str(python_exe), str(agent_script)],
            cwd=str(agent_script.parent.parent),
            env=env,
            creationflags=creationflags,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
        )
        _spawned_pids[user_id] = proc.pid
        print(
            f"[agent-starter] LAUNCHED local agent for user {user_id} "
            f"(pid={proc.pid}, token via env, ws={settings.AGENT_WS_URL}) -> log: {log_path}"
        )
        return True
    except Exception as e:
        print(f"[agent-starter] ERROR: Failed to launch agent for user {user_id}: {e}")
        return False
    finally:
        _spawning.discard(user_id)


async def terminate_agent_for_user(user_id: int) -> bool:
    """Terminate a previously auto-started agent process for this user.

    Called when all of the user's posts are done (posted/failed) so the
    agent's console window doesn't stay open forever.

    Returns True if a process was found and a termination was attempted.
    """
    pid = _spawned_pids.pop(user_id, None)
    if pid is None:
        return False
    try:
        import subprocess
        if sys.platform == "win32":
            # /T kills the whole process tree (Chrome children too),
            # /F forces it so the console window closes.
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                capture_output=True,
            )
        else:
            import signal
            import os
            os.kill(pid, signal.SIGTERM)
        print(f"[agent-starter] Terminated agent process {pid} for user {user_id}")
        return True
    except Exception as e:
        print(f"[agent-starter] WARN: Could not terminate agent {pid} for user {user_id}: {e}")
        return False