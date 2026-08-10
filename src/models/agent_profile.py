"""User agent profile model — stores per-user Chrome profile for the agent."""
from datetime import datetime, timezone

from sqlalchemy import String, DateTime, ForeignKey, Integer, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base


class UserAgentProfile(Base):
    """Stores the Chrome profile path for each user's agent.

    Each user gets their own Chrome profile so they can log into
    their own social media accounts (Instagram, Facebook, etc.)
    independently of other users.
    """

    __tablename__ = "accounts_useragentprofile"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("accounts_user.id", ondelete="CASCADE"), unique=True, index=True)
    # Chrome user-data-dir path (where Chrome stores profile data)
    user_data_dir: Mapped[str] = mapped_column(String(500))
    # Chrome profile directory name (e.g., "Default", "Profile 1")
    profile_directory: Mapped[str] = mapped_column(String(100), default="Default")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    user = relationship("User", back_populates="agent_profile")

    def __repr__(self):
        return f"<UserAgentProfile user={self.user_id} dir={self.user_data_dir}>"