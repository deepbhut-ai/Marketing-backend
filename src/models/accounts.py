"""SQLAlchemy models for the accounts app (User + AgentDevice)."""
import hashlib
import secrets
from datetime import datetime

from sqlalchemy import String, Boolean, DateTime, ForeignKey, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime, timezone

from src.core.database import Base


def _now():
    return datetime.now(timezone.utc)


class User(Base):
    """Custom user model — email-based login (mirrors accounts.User)."""

    __tablename__ = "accounts_user"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    password: Mapped[str] = mapped_column(String(255))  # Django's hashed password column
    last_login: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False)
    username: Mapped[str] = mapped_column(String(150), unique=True, index=True)
    first_name: Mapped[str] = mapped_column(String(150), default="")
    last_name: Mapped[str] = mapped_column(String(150), default="")
    is_staff: Mapped[bool] = mapped_column(Boolean, default=False)
    date_joined: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    phone_number: Mapped[str | None] = mapped_column(String(15), nullable=True)
    role: Mapped[str] = mapped_column(String(10), default="user")  # admin / user
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    # relationships
    agent_devices = relationship("AgentDevice", back_populates="user", cascade="all, delete-orphan")
    posts = relationship("Post", back_populates="user", cascade="all, delete-orphan")
    comments = relationship("PostComment", back_populates="user", cascade="all, delete-orphan")
    comment_settings = relationship("CommentSettings", back_populates="user", uselist=False, cascade="all, delete-orphan")
    content_plans = relationship("ContentPlan", back_populates="user", cascade="all, delete-orphan")
    ai_key = relationship("UserAIKey", back_populates="user", uselist=False, cascade="all, delete-orphan")
    agent_profile = relationship("UserAgentProfile", back_populates="user", uselist=False, cascade="all, delete-orphan")
    credit_logs = relationship("CreditLog", back_populates="user", cascade="all, delete-orphan")
    assets = relationship("Asset", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<User {self.email}>"


class AgentDevice(Base):
    """Agent device token (mirrors accounts.AgentDevice)."""

    __tablename__ = "accounts_agentdevice"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("accounts_user.id", ondelete="CASCADE"), index=True)
    device_name: Mapped[str] = mapped_column(String(255))
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    raw_token: Mapped[str | None] = mapped_column(String(128), nullable=True)  # Django stores this (security risk but kept for compat)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_online: Mapped[bool] = mapped_column(Boolean, default=False)
    last_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    user = relationship("User", back_populates="agent_devices")

    @staticmethod
    def generate_token() -> tuple[str, str]:
        """Returns (raw_token, token_hash). Store only the hash."""
        raw_token = secrets.token_urlsafe(48)
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        return raw_token, token_hash

    def __repr__(self):
        return f"<AgentDevice {self.device_name}>"