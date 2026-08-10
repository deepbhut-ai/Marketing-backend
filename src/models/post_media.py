"""PostMedia model — multiple media files per post."""
from datetime import datetime

from sqlalchemy import String, DateTime, ForeignKey, Integer, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base


class PostMedia(Base):
    __tablename__ = "posts_postmedia"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("posts_post.id", ondelete="CASCADE"), index=True)
    file: Mapped[str] = mapped_column(String(500))  # relative path under MEDIA_DIR
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        server_default=func.now(),
    )

    post = relationship("Post", back_populates="media_files")