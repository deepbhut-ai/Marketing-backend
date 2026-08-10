"""SQLAlchemy models for the credits app (CreditRate + CreditLog)."""
from datetime import datetime, timezone

from sqlalchemy import (
    String, Integer, Boolean, DateTime, ForeignKey, Text, JSON, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


# Well-known action keys (used as defaults / validation helpers).
ACTION_IMAGE_GENERATION = "image_generation"
ACTION_VIDEO_GENERATION = "video_generation"
ACTION_CAPTION_GENERATION = "caption_generation"
ACTION_CONTENT_PLAN_GENERATION = "content_plan_generation"

DEFAULT_ACTIONS = (
    ACTION_IMAGE_GENERATION,
    ACTION_VIDEO_GENERATION,
    ACTION_CAPTION_GENERATION,
    ACTION_CONTENT_PLAN_GENERATION,
)


class CreditRate(Base):
    """Per-operation credit cost. The 'price/rate' table.

    When a CreditLog is created, the `credits` value is looked up from
    this table by `action_key`.
    """

    __tablename__ = "credits_creditrate"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    action_key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    label: Mapped[str] = mapped_column(String(120), default="")
    credits: Mapped[int] = mapped_column(Integer, default=1)  # cost per use
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self):
        return f"<CreditRate {self.action_key}={self.credits}>"


class CreditLog(Base):
    """Record of a single credit 'cut' (usage). Log only — no balance."""

    __tablename__ = "credits_creditlog"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("accounts_user.id", ondelete="CASCADE"), index=True
    )
    action_key: Mapped[str] = mapped_column(String(64), index=True)
    credits_used: Mapped[int] = mapped_column(Integer, default=0)
    reference_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reference_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    user = relationship("User", back_populates="credit_logs")

    def __repr__(self):
        return f"<CreditLog user={self.user_id} action={self.action_key} -{self.credits_used}>"
