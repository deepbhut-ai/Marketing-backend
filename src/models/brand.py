"""SQLAlchemy model for the brand app (BrandProfile).

A user can have multiple BrandProfile rows (one per brand). Stores the
brand identity that feeds into image generation, caption generation,
and content plans.
"""
from datetime import datetime, timezone

from sqlalchemy import (
    String, Integer, DateTime, ForeignKey, Text, JSON, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class BrandProfile(Base):
    """Per-user brand profile (multiple brands per user allowed)."""

    __tablename__ = "brand_brandprofile"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("accounts_user.id", ondelete="CASCADE"), index=True,
    )
    brand_name: Mapped[str] = mapped_column(String(255), default="", index=True)
    industry: Mapped[str] = mapped_column(String(255), default="")
    website_url: Mapped[str] = mapped_column(String(500), default="")
    tone: Mapped[str] = mapped_column(String(255), default="")
    target_audience: Mapped[str] = mapped_column(String(500), default="")
    brand_summary: Mapped[str] = mapped_column(Text, default="")
    brand_keywords: Mapped[list] = mapped_column(JSON, default=list)
    primary_colors: Mapped[list] = mapped_column(JSON, default=list)  # ["#E8380E", ...]
    fonts: Mapped[list] = mapped_column(JSON, default=list)  # ["Helvetica Neue", ...]
    logo_asset_id: Mapped[int | None] = mapped_column(
        ForeignKey("assets_asset.id", ondelete="SET NULL"), nullable=True
    )
    hashtag_pool: Mapped[list] = mapped_column(JSON, default=list)  # ["#chipotle", ...]
    bio: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user = relationship("User", back_populates="brand_profile")
    logo_asset = relationship("Asset", foreign_keys=[logo_asset_id])

    def __repr__(self):
        return f"<BrandProfile user={self.user_id} brand={self.brand_name}>"