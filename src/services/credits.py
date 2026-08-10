"""Credit logging service — records usage at the point of generation.

Works in both async (FastAPI routers) and sync (Celery tasks) contexts.

Design:
- Looks up the cost from the CreditRate table by `action_key`.
- Creates one CreditLog row per call.
- **Silently skips** if no active CreditRate is configured (never raises,
  never blocks the actual generation — credits are a side-effect, the
  user's operation must still succeed).
- Returns the number of credits logged (0 if skipped).

Action keys (defined in src.models.credits):
- image_generation
- video_generation
- caption_generation
- content_plan_generation
"""
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from src.models.credits import CreditRate, CreditLog

logger = logging.getLogger(__name__)


async def log_credit_async(
    db: AsyncSession,
    user_id: int,
    action_key: str,
    *,
    reference_type: str | None = None,
    reference_id: int | None = None,
    meta: dict | None = None,
    note: str = "",
) -> int:
    """Async variant — for FastAPI routers.

    Adds a CreditLog to the given async session (caller commits).
    Returns credits logged (0 if skipped). Never raises.
    """
    try:
        result = await db.execute(
            select(CreditRate).where(CreditRate.action_key == action_key)
        )
        rate = result.scalar_one_or_none()
        if not rate or not rate.is_active:
            return 0
        db.add(CreditLog(
            user_id=user_id,
            action_key=action_key,
            credits_used=rate.credits,
            reference_type=reference_type,
            reference_id=reference_id,
            meta=meta,
            note=note,
        ))
        await db.flush()
        return rate.credits
    except Exception as e:
        logger.warning("log_credit_async skipped (%s): %s", action_key, e)
        return 0


def log_credit_sync(
    session: Session,
    user_id: int,
    action_key: str,
    *,
    reference_type: str | None = None,
    reference_id: int | None = None,
    meta: dict | None = None,
    note: str = "",
) -> int:
    """Sync variant — for Celery tasks.

    Adds a CreditLog to the given sync session (caller commits).
    Returns credits logged (0 if skipped). Never raises.
    """
    try:
        rate = session.execute(
            select(CreditRate).where(CreditRate.action_key == action_key)
        ).scalar_one_or_none()
        if not rate or not rate.is_active:
            return 0
        session.add(CreditLog(
            user_id=user_id,
            action_key=action_key,
            credits_used=rate.credits,
            reference_type=reference_type,
            reference_id=reference_id,
            meta=meta,
            note=note,
        ))
        session.flush()
        return rate.credits
    except Exception as e:
        logger.warning("log_credit_sync skipped (%s): %s", action_key, e)
        return 0
