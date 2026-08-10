"""Agent download + token + status router.

Provides:
  GET  /agent/download/         - Download the production agent.exe
  POST /agent/token/            - Generate (or get) the user's agent token
  GET  /agent/status/           - Check if the user's agent is online
  DELETE /agent/token/          - Revoke the user's agent token
"""
import os
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings, BASE_DIR
from src.core.database import get_db
from src.core.websocket_manager import registry
from src.dependencies.auth import get_current_user
from src.models.accounts import User, AgentDevice

router = APIRouter(prefix="/agent", tags=["agent"])

# Path to the built agent exe (standalone onefile build: dist/agent.exe)
# On Windows the build produces dist/agent.exe; on macOS/Linux it produces
# dist/agent (no extension). We check both so the download works regardless
# of which OS the build was run on.
_EXE_CANDIDATES = [
    BASE_DIR / "dist" / "agent.exe",   # Windows build
    BASE_DIR / "dist" / "agent",       # macOS / Linux build
]


def _find_agent_exe() -> Path | None:
    """Return the path to the built agent binary, or None if not found."""
    for candidate in _EXE_CANDIDATES:
        if candidate.exists() and candidate.is_file():
            return candidate
    return None


@router.get("/download/")
async def download_agent_exe(user: User = Depends(get_current_user)):
    """Download the production-ready agent executable.

    Serves the built agent binary (agent.exe on Windows, agent on macOS/Linux).
    The agent connects to wss://agents.zettalgor.com/ws/agent/ automatically.
    The user enters their agent token (from POST /agent/token/) when prompted.
    """
    exe_path = _find_agent_exe()
    if exe_path is None:
        raise HTTPException(
            status_code=404,
            detail="Agent exe not found. Run build_agent.bat first to build it.",
        )
    # Use the actual filename so the download keeps the right extension
    download_name = exe_path.name
    return FileResponse(
        path=str(exe_path),
        media_type="application/octet-stream",
        filename=download_name,
        headers={"Content-Disposition": f"attachment; filename={download_name}"},
    )


@router.post("/token/")
async def get_or_create_agent_token(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get or create the user's agent token.

    If the user already has an active agent device, returns its raw token.
    Otherwise, creates a new one. The raw token is only shown once — store it
    safely; the backend keeps only the hash.
    """
    # Check for an existing active device
    result = await db.execute(
        select(AgentDevice)
        .where(AgentDevice.user_id == user.id, AgentDevice.is_active == True)
        .order_by(AgentDevice.id.desc())
    )
    device = result.scalars().first()

    if device:
        # Return existing token if we still have the raw value
        if device.raw_token:
            return {
                "success": True,
                "message": "Agent token already exists",
                "data": {
                    "token": device.raw_token,
                    "device_name": device.device_name,
                    "is_online": registry.is_online(user.id),
                    "created_at": device.created_at.isoformat() if device.created_at else None,
                },
            }
        # Raw token was lost — revoke old device and create a new one
        device.is_active = False
        await db.flush()

    # Create a new device + token
    raw_token, token_hash = AgentDevice.generate_token()
    device = AgentDevice(
        user_id=user.id,
        device_name="Windows Agent",
        token_hash=token_hash,
        raw_token=raw_token,
        is_active=True,
        is_online=False,
    )
    db.add(device)
    await db.flush()

    return {
        "success": True,
        "message": "Agent token created",
        "data": {
            "token": raw_token,
            "device_name": device.device_name,
            "is_online": False,
            "created_at": device.created_at.isoformat() if device.created_at else None,
        },
    }


@router.get("/status/")
async def get_agent_status(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Check if the user's agent is currently connected (online/offline)."""
    result = await db.execute(
        select(AgentDevice)
        .where(AgentDevice.user_id == user.id, AgentDevice.is_active == True)
        .order_by(AgentDevice.id.desc())
    )
    device = result.scalars().first()

    if not device:
        return {
            "success": True,
            "data": {
                "configured": False,
                "is_online": False,
                "device_name": None,
                "last_seen": None,
            },
        }

    # Use the live WebSocket registry for real-time status
    online = registry.is_online(user.id)

    return {
        "success": True,
        "data": {
            "configured": True,
            "is_online": online,
            "device_name": device.device_name,
            "last_seen": device.last_seen.isoformat() if device.last_seen else None,
        },
    }


@router.delete("/token/")
async def revoke_agent_token(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Revoke the user's current agent token.

    The agent will need to get a new token via POST /agent/token/ to reconnect.
    """
    result = await db.execute(
        select(AgentDevice)
        .where(AgentDevice.user_id == user.id, AgentDevice.is_active == True)
        .order_by(AgentDevice.id.desc())
    )
    device = result.scalars().first()

    if device:
        device.is_active = False
        device.raw_token = None
        await db.flush()

    return {
        "success": True,
        "message": "Agent token revoked. Generate a new one via POST /agent/token/",
    }