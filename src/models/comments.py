"""SQLAlchemy models for the comments app (PostComment + CommentSettings)."""
from datetime import datetime

from sqlalchemy import String, DateTime, ForeignKey, Integer, Text, JSON, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base


class PostComment(Base):
    """A detected comment on a social-media post (mirrors comments.PostComment)."""

    __tablename__ = "comments_postcomment"

    STATUS_NEW = "new"
    STATUS_REPLY_PENDING = "reply_pending"
    STATUS_REPLY_SENT = "reply_sent"
    STATUS_REPLY_FAILED = "reply_failed"
    STATUS_IGNORED = "ignored"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("accounts_user.id", ondelete="CASCADE"), index=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("posts_post.id", ondelete="CASCADE"), index=True)
    platform: Mapped[str] = mapped_column(String(50))
    comment_id: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True, index=True)
    comment_author: Mapped[str | None] = mapped_column(String(255), nullable=True)
    comment_text: Mapped[str] = mapped_column(Text)
    comment_hash: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    reply_type: Mapped[str] = mapped_column(String(20), default="predefined")
    reply_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default=STATUS_NEW, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    replied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user = relationship("User", back_populates="comments")
    post = relationship("Post", back_populates="comments")


class CommentSettings(Base):
    """Per-user comment reply settings (mirrors comments.CommentSettings)."""

    __tablename__ = "comments_commentsettings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("accounts_user.id", ondelete="CASCADE"), unique=True, index=True)
    mode: Mapped[str] = mapped_column(String(10), default="AI")  # AI / MANUAL
    tone: Mapped[str] = mapped_column(String(20), default="friendly")
    keyword_replies: Mapped[dict] = mapped_column(JSON, default=dict)
    default_reply: Mapped[str] = mapped_column(Text, default="Thank you for your comment!")
    is_comment_detection_on: Mapped[bool] = mapped_column(default=True)

    user = relationship("User", back_populates="comment_settings")