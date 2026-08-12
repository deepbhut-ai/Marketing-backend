"""SQLAlchemy models for the posts app (Post + PostMedia + PostLog)."""
from datetime import datetime

from sqlalchemy import String, DateTime, ForeignKey, Integer, SmallInteger, Text, JSON, func
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
    post_logs = relationship("PostLog", back_populates="post", cascade="all, delete-orphan")


class PostLog(Base):
    """Audit log for post lifecycle events (creation, scheduling, regeneration, deletion).

    Records *what* happened to a post, *when*, and *by whom*. Unlike
    CreditLog (which tracks AI resource consumption), PostLog tracks the
    post's own lifecycle — every create / schedule / regenerate / delete
    gets a row here.
    """

    __tablename__ = "posts_postlog"

    # Well-known action values
    ACTION_CREATED = "created"
    ACTION_SCHEDULED = "scheduled"
    ACTION_REGENERATED_CAPTION = "regenerated_caption"
    ACTION_REGENERATED_IMAGE = "regenerated_image"
    ACTION_REGENERATED_VIDEO = "regenerated_video"
    ACTION_REGENERATED_DAY_GROUP = "regenerated_day_group"
    ACTION_DELETED = "deleted"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("accounts_user.id", ondelete="CASCADE"), index=True
    )
    post_id: Mapped[int | None] = mapped_column(
        ForeignKey("posts_post.id", ondelete="SET NULL"), nullable=True, index=True
    )
    action: Mapped[str] = mapped_column(String(64), index=True)
    platform: Mapped[str | None] = mapped_column(String(20), nullable=True)
    day_group_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    user = relationship("User", back_populates="post_logs")
    post = relationship("Post", back_populates="post_logs")

    def __repr__(self):
        return f"<PostLog user={self.user_id} post={self.post_id} action={self.action}>"