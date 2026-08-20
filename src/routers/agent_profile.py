"""Agent profile router — manage per-user Chrome profiles for the agent."""
import os
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.dependencies.auth import get_current_user
from src.core.websocket_manager import hash_token
from src.models.accounts import User, AgentDevice
from src.models.agent_profile import UserAgentProfile

router = APIRouter(prefix="/agent-profile", tags=["agent-profile"])

# Chrome paths on Windows
CHROME_PATHS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
]

# Base directory for all user Chrome profiles
PROFILE_BASE_DIR = os.path.join(
    os.environ.get("LOCALAPPDATA", os.path.expanduser("~")),
    "AutoSocialAI",
)

# Default platform login URLs
PLATFORM_URLS = {
    "instagram": "https://www.instagram.com/",
    "facebook": "https://www.facebook.com/",
    "linkedin": "https://www.linkedin.com/feed/",
    "x": "https://x.com/",
}


def _find_chrome() -> str | None:
    for path in CHROME_PATHS:
        if os.path.exists(path):
            return path
    return None


def _get_default_profile_dir(user_id: int) -> str:
    """Get the default Chrome profile path for a user."""
    return os.path.join(PROFILE_BASE_DIR, f"user_{user_id}")


@router.get("/by-token/")
async def get_profile_by_agent_token(
    token: str,
    db: AsyncSession = Depends(get_db),
):
    """Get the Chrome profile for the user associated with this agent token.

    The agent calls this with its raw token (no JWT needed) to fetch
    the correct Chrome profile directly from the database. This is the
    single source of truth for the agent's Chrome profile — it works for
    both auto-started and manually-started agents.
    """
    token_hash = hash_token(token)
    result = await db.execute(
        select(AgentDevice).where(
            AgentDevice.token_hash == token_hash,
            AgentDevice.is_active == True,
        )
    )
    device = result.scalar_one_or_none()
    if not device:
        raise HTTPException(status_code=403, detail="Invalid agent token")

    result = await db.execute(
        select(UserAgentProfile).where(UserAgentProfile.user_id == device.user_id)
    )
    profile = result.scalar_one_or_none()

    if not profile:
        # Auto-create default profile
        profile = UserAgentProfile(
            user_id=device.user_id,
            user_data_dir=_get_default_profile_dir(device.user_id),
            profile_directory="Default",
        )
        db.add(profile)
        await db.commit()
        await db.refresh(profile)

    # Ensure the profile directory exists so the agent can use it.
    try:
        os.makedirs(profile.user_data_dir, exist_ok=True)
    except Exception as e:
        print(f"[agent-profile] WARN: could not create profile dir {profile.user_data_dir}: {e}")

    return {
        "success": True,
        "data": {
            "user_id": profile.user_id,
            "user_data_dir": profile.user_data_dir,
            "profile_directory": profile.profile_directory,
        },
    }


@router.get("/")
async def get_agent_profile(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the current user's agent Chrome profile settings.

    Auto-creates a default profile if none exists.
    """
    result = await db.execute(
        select(UserAgentProfile).where(UserAgentProfile.user_id == user.id)
    )
    profile = result.scalar_one_or_none()

    if not profile:
        # Auto-create default profile for this user
        profile = UserAgentProfile(
            user_id=user.id,
            user_data_dir=_get_default_profile_dir(user.id),
            profile_directory="Default",
        )
        db.add(profile)
        await db.flush()

    return {
        "success": True,
        "message": "Agent profile fetched",
        "data": {
            "id": profile.id,
            "user_id": profile.user_id,
            "user_data_dir": profile.user_data_dir,
            "profile_directory": profile.profile_directory,
            "created_at": profile.created_at.isoformat() if profile.created_at else None,
            "updated_at": profile.updated_at.isoformat() if profile.updated_at else None,
        },
    }


@router.post("/open-chrome/")
async def open_chrome_for_login(
    data: dict,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Open Chrome with the user's own profile for pre-login.

    Pass a list of platforms to open, or omit to open all platforms.
    The user logs into each platform in Chrome, then closes it.

    Example body: {"platforms": ["instagram", "facebook"]}
    """
    platforms = data.get("platforms", list(PLATFORM_URLS.keys()))

    # Get or create the user's profile
    result = await db.execute(
        select(UserAgentProfile).where(UserAgentProfile.user_id == user.id)
    )
    profile = result.scalar_one_or_none()

    if not profile:
        profile = UserAgentProfile(
            user_id=user.id,
            user_data_dir=_get_default_profile_dir(user.id),
            profile_directory="Default",
        )
        db.add(profile)
        await db.flush()

    # Build URLs to open
    urls = [PLATFORM_URLS.get(p, "") for p in platforms if p in PLATFORM_URLS]
    if not urls:
        return {"success": False, "message": "No valid platforms specified"}

    chrome_path = _find_chrome()
    if not chrome_path:
        return {"success": False, "message": "Chrome not found on this machine"}

    # Ensure the profile directory exists
    os.makedirs(profile.user_data_dir, exist_ok=True)

    # Open Chrome with the user's own profile
    cmd = [
        chrome_path,
        f"--user-data-dir={profile.user_data_dir}",
        f"--profile-directory={profile.profile_directory}",
        *urls,
    ]
    subprocess.Popen(cmd)

    return {
        "success": True,
        "message": "Chrome opened with your profile. Log into each platform, then close Chrome.",
        "data": {
            "chrome_path": chrome_path,
            "user_data_dir": profile.user_data_dir,
            "profile_directory": profile.profile_directory,
            "urls_opened": urls,
        },
    }


@router.post("/update/")
async def update_agent_profile(
    data: dict,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update the user's Chrome profile settings.

    Example body: {"user_data_dir": "C:\\path\\to\\profile", "profile_directory": "Default"}
    """
    user_data_dir = data.get("user_data_dir")
    profile_directory = data.get("profile_directory", "Default")

    if not user_data_dir:
        return {"success": False, "message": "user_data_dir is required"}

    result = await db.execute(
        select(UserAgentProfile).where(UserAgentProfile.user_id == user.id)
    )
    profile = result.scalar_one_or_none()

    if not profile:
        profile = UserAgentProfile(
            user_id=user.id,
            user_data_dir=user_data_dir,
            profile_directory=profile_directory,
        )
        db.add(profile)
    else:
        profile.user_data_dir = user_data_dir
        profile.profile_directory = profile_directory
        profile.updated_at = datetime.now(timezone.utc)

    await db.flush()

    return {
        "success": True,
        "message": "Agent profile updated",
        "data": {
            "user_data_dir": profile.user_data_dir,
            "profile_directory": profile.profile_directory,
        },
    }


@router.post("/update-by-token/")
async def update_agent_profile_by_token(
    data: dict,
    db: AsyncSession = Depends(get_db),
):
    """Update the user's Chrome profile settings using agent token (no JWT).

    Called by the agent exe after the user selects/imports a profile.
    This updates the DB so the next by-token GET returns the correct
    path for THIS machine.

    Example body: {"token": "raw_agent_token", "user_data_dir": "C:\\path", "profile_directory": "Default"}
    """
    token = data.get("token")
    user_data_dir = data.get("user_data_dir")
    profile_directory = data.get("profile_directory", "Default")

    if not token:
        return {"success": False, "message": "token is required"}
    if not user_data_dir:
        return {"success": False, "message": "user_data_dir is required"}

    token_hash = hash_token(token)
    result = await db.execute(
        select(AgentDevice).where(
            AgentDevice.token_hash == token_hash,
            AgentDevice.is_active == True,
        )
    )
    device = result.scalar_one_or_none()
    if not device:
        raise HTTPException(status_code=403, detail="Invalid agent token")

    result = await db.execute(
        select(UserAgentProfile).where(UserAgentProfile.user_id == device.user_id)
    )
    profile = result.scalar_one_or_none()

    if not profile:
        profile = UserAgentProfile(
            user_id=device.user_id,
            user_data_dir=user_data_dir,
            profile_directory=profile_directory,
        )
        db.add(profile)
    else:
        profile.user_data_dir = user_data_dir
        profile.profile_directory = profile_directory
        profile.updated_at = datetime.now(timezone.utc)

    await db.commit()

    return {
        "success": True,
        "message": "Agent profile updated",
        "data": {
            "user_data_dir": profile.user_data_dir,
            "profile_directory": profile.profile_directory,
        },
    }


# ============================================================
#  SYSTEM CHROME PROFILE DETECTION & IMPORT
# ============================================================

def _get_real_chrome_user_data_dir() -> Path:
    """Return the real Chrome User Data directory on this machine."""
    return Path(os.environ["LOCALAPPDATA"]) / "Google" / "Chrome" / "User Data"


def _detect_chrome_profiles() -> list[dict]:
    """Detect all Chrome profiles on this machine.

    Reads Chrome's "Local State" JSON file to get:
    - Profile display names (e.g., "Person 1", "Zettalgor")
    - Associated Google account emails
    - Last active time (epoch timestamp)
    - Which profile was last used

    Returns a list of dicts sorted by most recently used first:
        [{"name": "Profile 7", "display_name": "Deep Bhut", "email": "deep@...",
          "is_last_used": True, "active_time": 1785410631.0, ...}]
    """
    base_path = _get_real_chrome_user_data_dir()

    if not base_path.exists():
        return []

    # Read Local State to get profile display names, emails, and last-used info
    local_state_path = base_path / "Local State"
    profile_info: dict = {}
    last_used: str = ""
    last_active_profiles: list[str] = []

    if local_state_path.exists():
        try:
            with open(local_state_path, "r", encoding="utf-8") as f:
                local_state = json.load(f)
            profile_info = local_state.get("profile", {}).get("info_cache", {})
            last_used = local_state.get("profile", {}).get("last_used", "")
            last_active_profiles = local_state.get("profile", {}).get("last_active_profiles", [])
        except Exception:
            pass

    profiles = []

    for folder in sorted(base_path.iterdir()):
        if not folder.is_dir():
            continue
        if folder.name != "Default" and not folder.name.startswith("Profile"):
            continue

        info = profile_info.get(folder.name, {})
        display_name = info.get("name", folder.name)
        email = info.get("user_name", "")
        gaia_name = info.get("gaia_name", "")
        gaia_given_name = info.get("gaia_given_name", "")
        active_time = info.get("active_time", 0)
        is_ephemeral = info.get("is_ephemeral", False)

        # Skip ephemeral/guest profiles
        if is_ephemeral:
            continue

        profiles.append({
            "name": folder.name,
            "display_name": display_name or gaia_name or folder.name,
            "email": email,
            "gaia_name": gaia_name,
            "gaia_given_name": gaia_given_name,
            "user_data_dir": str(base_path),
            "profile_directory": folder.name,
            "path": str(folder),
            "is_last_used": folder.name == last_used,
            "active_time": active_time,
            "last_active_rank": (
                len(last_active_profiles) - last_active_profiles.index(folder.name)
                if folder.name in last_active_profiles else 0
            ),
        })

    # Sort: last_used first, then by active_time descending
    profiles.sort(
        key=lambda p: (
            not p["is_last_used"],       # False (last_used) sorts before True
            -(p["active_time"] or 0),    # most recent active_time first
        )
    )

    return profiles


def _detect_autosocial_profiles() -> list[dict]:
    """Detect all AutoSocial AI profiles already created on this machine.

    These are per-user profile directories under LOCALAPPDATA\\AutoSocialAI.
    """
    base = Path(PROFILE_BASE_DIR)

    if not base.exists():
        return []

    profiles = []

    for folder in sorted(base.iterdir()):
        if not folder.is_dir():
            continue
        # Each folder is either "chrome_profile" or "user_<id>"
        default_profile = folder / "Default"
        has_profile = default_profile.exists() or any(
            p.is_dir() and (p.name == "Default" or p.name.startswith("Profile"))
            for p in folder.iterdir()
        )

        profiles.append({
            "name": folder.name,
            "display_name": folder.name.replace("user_", "User ").replace("_", " "),
            "user_data_dir": str(folder),
            "profile_directory": "Default",
            "path": str(folder),
            "is_autosocial": True,
            "has_profile_data": has_profile,
        })

    return profiles


@router.get("/system-profiles/")
async def list_system_chrome_profiles(
    user: User = Depends(get_current_user),
):
    """List all Chrome profiles available on this machine.

    Returns two lists:
    - `chrome_profiles`: Real Chrome profiles installed on the system
      (with display names and emails from Chrome's Local State).
    - `autosocial_profiles`: AutoSocial AI per-user profiles already created.

    The user can pick one and call /agent-profile/import-profile/ to
    import it for their agent.
    """
    try:
        chrome_profiles = _detect_chrome_profiles()
    except Exception as e:
        chrome_profiles = []

    try:
        autosocial_profiles = _detect_autosocial_profiles()
    except Exception as e:
        autosocial_profiles = []

    # Get the user's currently assigned profile
    return {
        "success": True,
        "message": "System Chrome profiles detected",
        "data": {
            "chrome_profiles": chrome_profiles,
            "autosocial_profiles": autosocial_profiles,
            "chrome_user_data_dir": str(_get_real_chrome_user_data_dir()),
            "autosocial_base_dir": PROFILE_BASE_DIR,
        },
    }


@router.get("/current-chrome-profile/")
async def get_current_chrome_profile(
    user: User = Depends(get_current_user),
):
    """Get the Chrome profile the user is currently using on their machine.

    Reads Chrome's "Local State" file to find the `last_used` profile —
    this is the profile that opens when the user launches Chrome normally.

    Returns the profile name, display name, email, and path so the
    frontend can show "You are currently using: Deep Bhut (deep@iraglobaltech.com)"
    and offer a one-click import.
    """
    try:
        profiles = _detect_chrome_profiles()
    except Exception:
        profiles = []

    if not profiles:
        return {
            "success": False,
            "message": "No Chrome profiles found on this machine",
        }

    # The first profile is already sorted to be the last-used one
    current = profiles[0]

    return {
        "success": True,
        "message": "Current Chrome profile detected",
        "data": {
            "name": current["name"],
            "display_name": current["display_name"],
            "email": current["email"],
            "gaia_name": current.get("gaia_name", ""),
            "user_data_dir": current["user_data_dir"],
            "profile_directory": current["profile_directory"],
            "is_last_used": current["is_last_used"],
            "active_time": current["active_time"],
        },
    }


@router.post("/import-profile/")
async def import_chrome_profile(
    data: dict,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Import an existing Chrome profile for the user's agent.

    Copies the selected Chrome profile (cookies, logins, etc.) into a
    dedicated AutoSocial profile directory for this user, so the agent
    can use the same social-media logins without affecting the user's
    normal Chrome.

    Example body:
        {"profile_name": "Default"}
        {"profile_name": "Profile 1"}

    The profile_name must be one of the values returned by
    /agent-profile/system-profiles/ → chrome_profiles[].name
    """
    profile_name = data.get("profile_name")
    if not profile_name:
        return {"success": False, "message": "profile_name is required"}

    chrome_user_data_dir = _get_real_chrome_user_data_dir()
    source_profile_path = chrome_user_data_dir / profile_name

    if not source_profile_path.exists():
        return {
            "success": False,
            "message": f"Chrome profile '{profile_name}' not found at {source_profile_path}",
        }

    # Target: per-user AutoSocial profile directory
    target_user_data_dir = _get_default_profile_dir(user.id)
    target_profile_path = Path(target_user_data_dir) / "Default"

    # Files/folders to skip (locked, cache, or not needed)
    ignore_names = {
        "SingletonLock", "SingletonSocket", "SingletonCookie",
        "Crashpad", "ShaderCache", "GrShaderCache", "GPUCache",
        "Code Cache", "BrowserMetrics", "OptimizationGuidePredictionModels",
        "Safe Browsing", "CertificateRevocation",
    }

    # Clean target if it exists
    if target_profile_path.exists():
        shutil.rmtree(target_profile_path, ignore_errors=True)
    target_profile_path.mkdir(parents=True, exist_ok=True)

    # Copy profile data (skip locked/cache files)
    copied_count = 0
    skipped_count = 0
    for root, dirs, files in os.walk(source_profile_path):
        root_path = Path(root)
        relative_path = root_path.relative_to(source_profile_path)
        target_root = target_profile_path / relative_path
        target_root.mkdir(parents=True, exist_ok=True)

        dirs[:] = [d for d in dirs if d not in ignore_names]

        for file_name in files:
            if file_name in ignore_names:
                continue
            source_file = root_path / file_name
            target_file = target_root / file_name
            try:
                shutil.copy2(str(source_file), str(target_file))
                copied_count += 1
            except (PermissionError, OSError):
                skipped_count += 1

    # Also copy Local State (needed for Chrome to recognize profiles)
    local_state_file = chrome_user_data_dir / "Local State"
    if local_state_file.exists():
        try:
            shutil.copy2(str(local_state_file), str(Path(target_user_data_dir) / "Local State"))
        except Exception:
            pass

    # Update the user's profile in DB
    result = await db.execute(
        select(UserAgentProfile).where(UserAgentProfile.user_id == user.id)
    )
    profile = result.scalar_one_or_none()

    if not profile:
        profile = UserAgentProfile(
            user_id=user.id,
            user_data_dir=target_user_data_dir,
            profile_directory="Default",
        )
        db.add(profile)
    else:
        profile.user_data_dir = target_user_data_dir
        profile.profile_directory = "Default"
        profile.updated_at = datetime.now(timezone.utc)

    await db.commit()

    return {
        "success": True,
        "message": f"Chrome profile '{profile_name}' imported successfully",
        "data": {
            "source_profile": str(source_profile_path),
            "target_user_data_dir": target_user_data_dir,
            "profile_directory": "Default",
            "files_copied": copied_count,
            "files_skipped": skipped_count,
        },
    }


@router.get("/system-profiles/by-token/")
async def list_system_profiles_by_token(
    token: str,
    db: AsyncSession = Depends(get_db),
):
    """List Chrome profiles on this machine, authenticated by agent token.

    This is called by the agent exe (which doesn't have a JWT) to
    discover available Chrome profiles on the machine it's running on.
    The agent can then show them to the user for selection.
    """
    token_hash = hash_token(token)
    result = await db.execute(
        select(AgentDevice).where(
            AgentDevice.token_hash == token_hash,
            AgentDevice.is_active == True,
        )
    )
    device = result.scalar_one_or_none()
    if not device:
        raise HTTPException(status_code=403, detail="Invalid agent token")

    try:
        chrome_profiles = _detect_chrome_profiles()
    except Exception:
        chrome_profiles = []

    try:
        autosocial_profiles = _detect_autosocial_profiles()
    except Exception:
        autosocial_profiles = []

    # Include the user's current profile
    result = await db.execute(
        select(UserAgentProfile).where(UserAgentProfile.user_id == device.user_id)
    )
    profile = result.scalar_one_or_none()
    current_profile = None
    if profile:
        current_profile = {
            "user_data_dir": profile.user_data_dir,
            "profile_directory": profile.profile_directory,
        }

    return {
        "success": True,
        "data": {
            "user_id": device.user_id,
            "chrome_profiles": chrome_profiles,
            "autosocial_profiles": autosocial_profiles,
            "current_profile": current_profile,
            "chrome_user_data_dir": str(_get_real_chrome_user_data_dir()),
            "autosocial_base_dir": PROFILE_BASE_DIR,
        },
    }


@router.get("/current-chrome-profile/by-token/")
async def get_current_chrome_profile_by_token(
    token: str,
    db: AsyncSession = Depends(get_db),
):
    """Get the Chrome profile the user is currently using (agent token auth).

    Called by the agent exe to detect which Chrome profile the user
    last opened on their machine. The agent can then auto-import it
    or show "Currently using: Deep Bhut (deep@iraglobaltech.com)".
    """
    token_hash = hash_token(token)
    result = await db.execute(
        select(AgentDevice).where(
            AgentDevice.token_hash == token_hash,
            AgentDevice.is_active == True,
        )
    )
    device = result.scalar_one_or_none()
    if not device:
        raise HTTPException(status_code=403, detail="Invalid agent token")

    try:
        profiles = _detect_chrome_profiles()
    except Exception:
        profiles = []

    if not profiles:
        return {
            "success": False,
            "message": "No Chrome profiles found on this machine",
            "data": {"user_id": device.user_id},
        }

    current = profiles[0]

    return {
        "success": True,
        "message": "Current Chrome profile detected",
        "data": {
            "user_id": device.user_id,
            "name": current["name"],
            "display_name": current["display_name"],
            "email": current["email"],
            "gaia_name": current.get("gaia_name", ""),
            "user_data_dir": current["user_data_dir"],
            "profile_directory": current["profile_directory"],
            "is_last_used": current["is_last_used"],
            "active_time": current["active_time"],
        },
    }


@router.post("/import-profile/by-token/")
async def import_profile_by_token(
    data: dict,
    db: AsyncSession = Depends(get_db),
):
    """Import a Chrome profile for the user associated with this agent token.

    Called by the agent exe (no JWT). The agent passes its raw token
    and the Chrome profile name to import.

    Example body:
        {"token": "raw_agent_token", "profile_name": "Default"}
    """
    token = data.get("token")
    profile_name = data.get("profile_name")

    if not token or not profile_name:
        return {"success": False, "message": "token and profile_name are required"}

    token_hash = hash_token(token)
    result = await db.execute(
        select(AgentDevice).where(
            AgentDevice.token_hash == token_hash,
            AgentDevice.is_active == True,
        )
    )
    device = result.scalar_one_or_none()
    if not device:
        raise HTTPException(status_code=403, detail="Invalid agent token")

    user_id = device.user_id

    chrome_user_data_dir = _get_real_chrome_user_data_dir()
    source_profile_path = chrome_user_data_dir / profile_name

    if not source_profile_path.exists():
        return {
            "success": False,
            "message": f"Chrome profile '{profile_name}' not found",
        }

    target_user_data_dir = _get_default_profile_dir(user_id)
    target_profile_path = Path(target_user_data_dir) / "Default"

    ignore_names = {
        "SingletonLock", "SingletonSocket", "SingletonCookie",
        "Crashpad", "ShaderCache", "GrShaderCache", "GPUCache",
        "Code Cache", "BrowserMetrics", "OptimizationGuidePredictionModels",
        "Safe Browsing", "CertificateRevocation",
    }

    if target_profile_path.exists():
        shutil.rmtree(target_profile_path, ignore_errors=True)
    target_profile_path.mkdir(parents=True, exist_ok=True)

    copied_count = 0
    skipped_count = 0
    for root, dirs, files in os.walk(source_profile_path):
        root_path = Path(root)
        relative_path = root_path.relative_to(source_profile_path)
        target_root = target_profile_path / relative_path
        target_root.mkdir(parents=True, exist_ok=True)

        dirs[:] = [d for d in dirs if d not in ignore_names]

        for file_name in files:
            if file_name in ignore_names:
                continue
            source_file = root_path / file_name
            target_file = target_root / file_name
            try:
                shutil.copy2(str(source_file), str(target_file))
                copied_count += 1
            except (PermissionError, OSError):
                skipped_count += 1

    local_state_file = chrome_user_data_dir / "Local State"
    if local_state_file.exists():
        try:
            shutil.copy2(str(local_state_file), str(Path(target_user_data_dir) / "Local State"))
        except Exception:
            pass

    # Update DB
    result = await db.execute(
        select(UserAgentProfile).where(UserAgentProfile.user_id == user_id)
    )
    profile = result.scalar_one_or_none()

    if not profile:
        profile = UserAgentProfile(
            user_id=user_id,
            user_data_dir=target_user_data_dir,
            profile_directory="Default",
        )
        db.add(profile)
    else:
        profile.user_data_dir = target_user_data_dir
        profile.profile_directory = "Default"
        profile.updated_at = datetime.now(timezone.utc)

    await db.commit()

    return {
        "success": True,
        "message": f"Chrome profile '{profile_name}' imported for user {user_id}",
        "data": {
            "user_id": user_id,
            "target_user_data_dir": target_user_data_dir,
            "profile_directory": "Default",
            "files_copied": copied_count,
            "files_skipped": skipped_count,
        },
    }