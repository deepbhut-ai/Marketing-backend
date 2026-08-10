"""Pydantic schemas for the accounts app."""
from datetime import datetime
from pydantic import BaseModel, EmailStr, Field, ConfigDict


# ── Request schemas ──────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=150)
    email: EmailStr
    password: str = Field(..., min_length=6)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    device_name: str = "My Device"


# ── Response schemas ─────────────────────────────────────────────────

class RegisterResponse(BaseModel):
    success: bool
    message: str
    data: dict


class LoginData(BaseModel):
    user_id: int
    access: str
    refresh: str
    device_id: int
    agent_token: str
    type: str  # user role: "admin" or "user"


class LoginResponse(BaseModel):
    success: bool
    message: str
    data: LoginData


class AgentTokenResponse(BaseModel):
    success: bool
    device_id: int
    agent_token: str


class RefreshRequest(BaseModel):
    refresh: str


class RefreshResponse(BaseModel):
    success: bool = True
    access: str
    refresh: str