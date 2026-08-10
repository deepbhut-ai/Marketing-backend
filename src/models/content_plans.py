"""SQLAlchemy models for the content_plans app."""
from datetime import datetime, date, time, timezone

from sqlalchemy import (
    String, DateTime, Date, Time, ForeignKey, Integer, Text, JSON,
    LargeBinary, SmallInteger, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base


class ContentPlan(Base):
    """Top-level bulk content plan owned by a user."""

    __tablename__ = "content_plans_contentplan"

    STATUS_DRAFT = "draft"
    STATUS_GENERATING = "generating"
    STATUS_PENDING_REVIEW = "pending_review"
    STATUS_APPROVED = "approved"
    STATUS_SCHEDULED = "scheduled"
    STATUS_FAILED = "failed"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("accounts_user.id", ondelete="CASCADE"), index=True)
    website_url: Mapped[str] = mapped_column(String(500))
    duration_days: Mapped[int] = mapped_column(SmallInteger)
    platforms: Mapped[list] = mapped_column(JSON, default=list)
    frequency: Mapped[str] = mapped_column(String(20), default="daily")
    custom_interval_days: Mapped[int] = mapped_column(SmallInteger, default=1)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    posting_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    media_type: Mapped[str] = mapped_column(String(10), default="image")
    image_model: Mapped[str] = mapped_column(String(64), default="")
    video_model: Mapped[str] = mapped_column(String(64), default="")
    brand_summary: Mapped[str] = mapped_column(Text, default="")
    brand_keywords: Mapped[list] = mapped_column(JSON, default=list)
    total_posts: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default=STATUS_DRAFT, index=True)
    progress: Mapped[int] = mapped_column(SmallInteger, default=0)
    error_message: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user = relationship("User", back_populates="content_plans")
    items = relationship("ContentPlanItem", back_populates="plan", cascade="all, delete-orphan",
                         order_by="ContentPlanItem.sequence, ContentPlanItem.id")


class ContentPlanItem(Base):
    """A single generated draft post inside a plan."""

    __tablename__ = "content_plans_contentplanitem"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("content_plans_contentplan.id", ondelete="CASCADE"), index=True)
    sequence: Mapped[int] = mapped_column(SmallInteger)
    platform: Mapped[str] = mapped_column(String(20))
    topic: Mapped[str] = mapped_column(String(255), default="")
    caption: Mapped[str] = mapped_column(Text, default="")
    hashtags: Mapped[str] = mapped_column(Text, default="")
    image: Mapped[str | None] = mapped_column(String(500), nullable=True)  # relative path
    image_prompt: Mapped[str] = mapped_column(Text, default="")
    video: Mapped[str | None] = mapped_column(String(500), nullable=True)
    video_prompt: Mapped[str] = mapped_column(Text, default="")
    video_operation: Mapped[str] = mapped_column(String(255), default="")
    media_type: Mapped[str] = mapped_column(String(10), default="image")
    scheduled_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="pending_review", index=True)
    post_id: Mapped[int | None] = mapped_column(ForeignKey("posts_post.id", ondelete="SET NULL"), nullable=True)
    caption_regen_count: Mapped[int] = mapped_column(SmallInteger, default=0)
    image_regen_count: Mapped[int] = mapped_column(SmallInteger, default=0)
    video_regen_count: Mapped[int] = mapped_column(SmallInteger, default=0)
    error_message: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    plan = relationship("ContentPlan", back_populates="items")
    post = relationship("Post", foreign_keys=[post_id])


class UserAIKey(Base):
    """Encrypted per-user storage for third-party AI API keys."""

    __tablename__ = "content_plans_useraikey"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("accounts_user.id", ondelete="CASCADE"), unique=True, index=True)
    gemini_key_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    gemini_key_last4: Mapped[str] = mapped_column(String(4), default="")
    gemini_validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    default_image_model: Mapped[str] = mapped_column(String(64), default="")
    default_video_model: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), server_default=func.now(), onupdate=func.now())

    user = relationship("User", back_populates="ai_key")