"""SQLAlchemy models for the posts app (Post + PostMedia)."""
from datetime import datetime

from sqlalchemy import String, DateTime, ForeignKey, Integer, SmallInteger, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base


class Post(Base):
    """Stores post data for automation (mirrors posts.Post)."""

    __tablename__ = "posts_post"

    STATUS_PENDING = "pending"
    STATUS_SCHEDULED = "scheduled"
    STATUS_PROCESSING = "processing"
    STATUS_POSTED = "posted"
    STATUS_FAILED = "failed"

    STATUS_CHOICES = (
        ("pending", "Pending"),
        ("scheduled", "Scheduled"),
        ("processing", "Processing"),
        ("posted", "Posted"),
        ("failed", "Failed"),
    )

    PLATFORM_CHOICES = (
        ("facebook", "Facebook"),
        ("instagram", "Instagram"),
        ("linkedin", "LinkedIn"),
        ("x", "X"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("accounts_user.id", ondelete="CASCADE"), index=True)
    caption: Mapped[str] = mapped_column(Text)
    media: Mapped[str | None] = mapped_column(String(500), nullable=True)  # legacy single-file field
    platform: Mapped[str] = mapped_column(String(20))
    scheduled_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), default=STATUS_PENDING, index=True)
    post_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    platform_post_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    day_group_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)  # UUID grouping all platform posts for the same day
    # Regeneration counters — track how many times a user has regenerated
    # the caption / image / video for this post (analytics only; no limit).
    caption_regen_count: Mapped[int] = mapped_column(SmallInteger, default=0)
    image_regen_count: Mapped[int] = mapped_column(SmallInteger, default=0)
    video_regen_count: Mapped[int] = mapped_column(SmallInteger, default=0)

    user = relationship("User", back_populates="posts")
    media_files = relationship("PostMedia", back_populates="post", cascade="all, delete-orphan")
    comments = relationship("PostComment", back_populates="post", cascade="all, delete-orphan")