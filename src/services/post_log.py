"""Post lifecycle logging service — records post creation / scheduling /
regeneration / deletion events.

Mirrors the design of ``src.services.credits``:
- Adds a PostLog row to the given session (caller commits).
- **Never raises** — logging is a side-effect and must not break the
  actual post operation.
"""
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from src.models.posts import PostLog

logger = logging.getLogger(__name__)


async def log_post_event(
    db: AsyncSession,
    user_id: int,
    action: str,
    *,
    post_id: int | None = None,
    platform: str | None = None,
    day_group_id: str | None = None,
    meta: dict | None = None,
    note: str = "",
) -> None:
    """Record a post lifecycle event.

    Adds a PostLog to the given async session (caller commits).
    Never raises — failures are logged and swallowed.
    """
    try:
        db.add(PostLog(
            user_id=user_id,
            post_id=post_id,
            action=action,
            platform=platform,
            day_group_id=day_group_id,
            meta=meta,
            note=note,
        ))
        await db.flush()
    except Exception as e:
        logger.warning("log_post_event skipped (%s): %s", action, e)