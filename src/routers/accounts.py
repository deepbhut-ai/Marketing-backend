"""Accounts router — register, login, generate-agent-token, refresh."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.security import hash_password, verify_password
from src.core.jwt_utils import create_access_token, create_refresh_token, decode_token
from src.dependencies.auth import get_current_user
from src.models.accounts import User, AgentDevice
from src.schemas.accounts import (
    RegisterRequest, LoginRequest, RefreshRequest,
)

router = APIRouter(prefix="/accounts", tags=["accounts"])


@router.post("/register/")
async def register_user(data: RegisterRequest, db: AsyncSession = Depends(get_db)):
    try:
        user = User(
            username=data.username,
            email=data.email,
            password=hash_password(data.password),
        )
        db.add(user)
        await db.flush()
        return {
            "success": True,
            "message": "User registration successfully done",
            "data": {"user_id": user.id, "type": user.role},
        }
    except Exception as e:
        await db.rollback()
        return {"success": False, "message": str(e)}, 400


@router.post("/login/")
async def login_user(data: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == data.email))
    user = result.scalar_one_or_none()

    if not user or not verify_password(data.password, user.password):
        return {"success": False, "message": "Invalid credential"}, 400

    access = create_access_token(user.id)
    refresh = create_refresh_token(user.id)

    # Create agent device + token
    raw_token, token_hash = AgentDevice.generate_token()
    device = AgentDevice(
        user_id=user.id,
        device_name=data.device_name,
        token_hash=token_hash,
        raw_token=raw_token,
    )
    db.add(device)
    await db.flush()

    return {
        "success": True,
        "message": "Login successfully done",
        "data": {
            "user_id": user.id,
            "access": access,
            "refresh": refresh,
            "device_id": device.id,
            "agent_token": raw_token,
            "type": user.role,  # "admin" or "user"
        },
    }


@router.get("/generate-agent-token/")
async def generate_agent_token(
    device_name: str = "My Device",
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    raw_token, token_hash = AgentDevice.generate_token()
    device = AgentDevice(
        user_id=user.id,
        device_name=device_name,
        token_hash=token_hash,
        raw_token=raw_token,
    )
    db.add(device)
    await db.flush()
    return {
        "success": True,
        "device_id": device.id,
        "agent_token": raw_token,
    }


@router.post("/refresh/")
async def refresh_token(data: RefreshRequest):
    user_id = decode_token(data.refresh)
    if user_id is None:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    access = create_access_token(user_id)
    refresh = create_refresh_token(user_id)
    return {"success": True, "access": access, "refresh": refresh}


# Also register at /api/token/refresh/ to match the Django URL exactly
@router.post("/api/token/refresh/", include_in_schema=False)
async def refresh_token_django_path(data: RefreshRequest):
    return await refresh_token(data)