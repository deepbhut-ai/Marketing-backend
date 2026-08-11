"""SQLAlchemy model for the assets app (Asset).

An Asset is a reusable piece of media owned by a user. The metadata
(name, type, tags, ...) lives in the DB; the binary itself is stored
on disk under `media/assets/<user_id>/<filename>` and referenced by the
relative `file` column (same convention as PostMedia / content_plans).
An optional external `url` is supported for assets that live elsewhere.
"""
from datetime import datetime, timezone

from sqlalchemy import (
    String, Integer, BigInteger, DateTime, ForeignKey, Text, JSON, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.config import settings
from src.core.database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


# Well-known asset type keys.
ASSET_TYPE_IMAGE = "image"
ASSET_TYPE_VIDEO = "video"
ASSET_TYPE_GIF = "gif"
ASSET_TYPE_DOCUMENT = "document"
ASSET_TYPE_AUDIO = "audio"
ASSET_TYPE_LINK = "link"

ASSET_TYPES = (
    ASSET_TYPE_IMAGE,
    ASSET_TYPE_VIDEO,
    ASSET_TYPE_GIF,
    ASSET_TYPE_DOCUMENT,
    ASSET_TYPE_AUDIO,
    ASSET_TYPE_LINK,
)

# Allowed source values. Only these two are accepted.
ASSET_SOURCE_UPLOADED = "uploaded"
ASSET_SOURCE_AI = "ai"
ASSET_SOURCES = (ASSET_SOURCE_UPLOADED, ASSET_SOURCE_AI)

# Mime-type -> extension hint for uploads.
EXT_BY_TYPE = {
    ASSET_TYPE_IMAGE: ".png",
    ASSET_TYPE_VIDEO: ".mp4",
    ASSET_TYPE_GIF: ".gif",
    ASSET_TYPE_DOCUMENT: ".pdf",
    ASSET_TYPE_AUDIO: ".mp3",
    ASSET_TYPE_LINK: "",
}


class Asset(Base):
    """Reusable media asset owned by a user.

    Storage modes:
      - source="uploaded" → binary under MEDIA_DIR/assets/... ; `file` set
      - source="ai"       → AI-generated image (binary under MEDIA_DIR/assets/...)
    """

    __tablename__ = "assets_asset"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("accounts_user.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    asset_type: Mapped[str] = mapped_column(String(20), index=True)
    # Relative path under MEDIA_DIR for uploaded / AI-generated files
    # (e.g. "assets/12/7-1699999999.png").
    file: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Optional URL (e.g. for AI-generated assets served from a CDN).
    url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    thumbnail_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    mime_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    file_size: Mapped[int | None] = mapped_column(BigInteger, nullable=True)  # bytes
    source: Mapped[str] = mapped_column(String(20), default="uploaded")  # uploaded | ai
    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    tags: Mapped[list | None] = mapped_column(JSON, nullable=True)
    meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    is_favorite: Mapped[bool] = mapped_column(default=False)
    is_archived: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user = relationship("User", back_populates="assets")

    def public_url(self) -> str | None:
        """Absolute URL to serve this asset (joined with BASE_URL + MEDIA prefix)."""
        if self.file:
            return f"{settings.BASE_URL}{settings.MEDIA_URL_PREFIX}/{self.file}"
        return self.url

    def __repr__(self):
        return f"<Asset {self.id} {self.asset_type} user={self.user_id}>"
