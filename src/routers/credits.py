"""Credits router — CRUD for CreditRate (admin) and CreditLog (user).

Convention mirrors `content_plans.py`:
- `_ok()` / `_err()` response helpers
- `get_current_user` for auth
- Admin-only endpoints check `user.role == "admin"`
"""
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.dependencies.auth import get_current_user
from src.models.accounts import User
from src.models.credits import CreditRate, CreditLog, DEFAULT_ACTIONS
from src.models.credits import (
    ACTION_IMAGE_GENERATION, ACTION_VIDEO_GENERATION, ACTION_CAPTION_GENERATION,
)
from src.models.posts import PostLog
from src.schemas.credits import (
    CreditRateCreate, CreditRateUpdate, CreditRateOut,
    CreditLogCreate, CreditLogOut, CreditLogListOut, CreditUsageSummary,
)

router = APIRouter(prefix="/api/credits", tags=["credits"])

# ── log_type → action_key mapping ────────────────────────────────────
# The four log types the frontend can filter by:
#   post    → PostLog table (post lifecycle events)
#   image   → CreditLog where action_key = image_generation
#   video   → CreditLog where action_key = video_generation
#   caption → CreditLog where action_key = caption_generation
LOG_TYPE_TO_ACTION_KEY: dict[str, str | None] = {
    "image": ACTION_IMAGE_GENERATION,
    "video": ACTION_VIDEO_GENERATION,
    "caption": ACTION_CAPTION_GENERATION,
    # "post" is handled separately — it queries the PostLog table
}
VALID_LOG_TYPES = ("post", "image", "video", "caption")


# ── helpers ──────────────────────────────────────────────────────────

def _ok(data: Any = None, message: str = "OK", http: int = 200):
    payload: dict[str, Any] = {"success": True, "message": message}
    if data is not None:
        payload["data"] = data
    return payload


def _err(message: str, errors: Any = None, http: int = 400):
    return {"success": False, "message": message, "errors": errors or {}}, http


def _require_admin(user: User):
    if user.role != "admin":
        return _err("Admin access required", http=403)
    return None


def _rate_to_dict(rate: CreditRate) -> dict:
    return {
        "id": rate.id,
        "action_key": rate.action_key,
        "label": rate.label,
        "credits": rate.credits,
        "is_active": rate.is_active,
        "created_at": rate.created_at.isoformat() if rate.created_at else None,
        "updated_at": rate.updated_at.isoformat() if rate.updated_at else None,
    }


def _log_to_dict(log: CreditLog) -> dict:
    return {
        "id": log.id,
        "user_id": log.user_id,
        "action_key": log.action_key,
        "credits_used": log.credits_used,
        "reference_type": log.reference_type,
        "reference_id": log.reference_id,
        "meta": log.meta,
        "note": log.note or "",
        "created_at": log.created_at.isoformat() if log.created_at else None,
    }


# ── CreditRate: admin CRUD ───────────────────────────────────────────

@router.get("/rates")
async def list_rates(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all credit rates. (Any authenticated user can read.)"""
    result = await db.execute(select(CreditRate).order_by(CreditRate.action_key))
    rates = result.scalars().all()
    return _ok([_rate_to_dict(r) for r in rates])


@router.post("/rates")
async def create_rate(
    payload: CreditRateCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a credit rate. Admin only."""
    denied = _require_admin(user)
    if denied:
        return denied

    exists = await db.execute(
        select(CreditRate).where(CreditRate.action_key == payload.action_key)
    )
    if exists.scalar_one_or_none():
        return _err(f"Rate for '{payload.action_key}' already exists", http=409)

    rate = CreditRate(
        action_key=payload.action_key,
        label=payload.label or payload.action_key,
        credits=payload.credits,
        is_active=payload.is_active,
    )
    db.add(rate)
    await db.flush()
    await db.refresh(rate)
    return _ok(_rate_to_dict(rate), message="Rate created", http=201), 201


@router.put("/rates/{rate_id}")
async def update_rate(
    rate_id: int,
    payload: CreditRateUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a credit rate. Admin only."""
    denied = _require_admin(user)
    if denied:
        return denied

    result = await db.execute(select(CreditRate).where(CreditRate.id == rate_id))
    rate = result.scalar_one_or_none()
    if not rate:
        return _err("Rate not found", http=404)

    data = payload.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(rate, k, v)
    await db.flush()
    await db.refresh(rate)
    return _ok(_rate_to_dict(rate), message="Rate updated")


@router.delete("/rates/{rate_id}")
async def delete_rate(
    rate_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a credit rate. Admin only."""
    denied = _require_admin(user)
    if denied:
        return denied

    result = await db.execute(select(CreditRate).where(CreditRate.id == rate_id))
    rate = result.scalar_one_or_none()
    if not rate:
        return _err("Rate not found", http=404)

    await db.delete(rate)
    await db.flush()
    return _ok(message="Rate deleted")


@router.post("/rates/seed-defaults")
async def seed_default_rates(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create the four default rates if missing. Admin only.

    Defaults: image_generation=5, video_generation=10,
    caption_generation=1, content_plan_generation=15.
    """
    denied = _require_admin(user)
    if denied:
        return denied

    defaults = {
        "image_generation": ("AI Image Generation", 5),
        "video_generation": ("AI Video Generation", 10),
        "caption_generation": ("Caption / Hashtag Generation", 1),
        "content_plan_generation": ("Content Plan Generation", 15),
    }

    existing = await db.execute(select(CreditRate))
    existing_keys = {r.action_key for r in existing.scalars().all()}

    created = []
    for key, (label, credits) in defaults.items():
        if key not in existing_keys:
            rate = CreditRate(action_key=key, label=label, credits=credits)
            db.add(rate)
            created.append(key)

    if created:
        await db.flush()
    return _ok({"created": created, "existing": sorted(existing_keys)},
               message=f"Seeded {len(created)} default rate(s)")


# ── CreditLog: user CRUD ─────────────────────────────────────────────

@router.get("/logs")
async def list_logs(
    action_key: str | None = Query(None, description="Filter by action_key (image_generation / video_generation / caption_generation)"),
    log_type: str | None = Query(None, description="Filter by log type: post / image / video / caption"),
    start_date: datetime | None = Query(None, description="ISO datetime lower bound"),
    end_date: datetime | None = Query(None, description="ISO datetime upper bound"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List the current user's credit logs (paginated, filterable).

    Supports two filter modes:
    - ``action_key``: direct filter on CreditLog.action_key (legacy).
    - ``log_type``: semantic filter — ``post`` queries the PostLog table,
      while ``image`` / ``video`` / ``caption`` map to the corresponding
      CreditLog action_key.
    If both are given, ``log_type`` takes precedence.
    """
    # ── log_type=post → query PostLog table ──────────────────────────
    if log_type == "post":
        base = select(PostLog).where(PostLog.user_id == user.id)
        if start_date:
            base = base.where(PostLog.created_at >= start_date)
        if end_date:
            base = base.where(PostLog.created_at <= end_date)

        count_q = select(func.count()).select_from(base.subquery())
        total = (await db.execute(count_q)).scalar_one()

        rows_q = (
            base.order_by(PostLog.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        logs = (await db.execute(rows_q)).scalars().all()

        items = [
            {
                "id": log.id,
                "user_id": log.user_id,
                "log_type": "post",
                "action": log.action,
                "post_id": log.post_id,
                "platform": log.platform,
                "day_group_id": log.day_group_id,
                "credits_used": 0,  # PostLog has no credits
                "reference_type": "post",
                "reference_id": log.post_id,
                "meta": log.meta,
                "note": log.note or "",
                "created_at": log.created_at.isoformat() if log.created_at else None,
            }
            for log in logs
        ]
        return _ok({
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
        })

    # ── log_type=image/video/caption → map to action_key ─────────────
    effective_action_key = action_key
    if log_type and log_type in LOG_TYPE_TO_ACTION_KEY:
        effective_action_key = LOG_TYPE_TO_ACTION_KEY[log_type]

    base = select(CreditLog).where(CreditLog.user_id == user.id)

    if effective_action_key:
        base = base.where(CreditLog.action_key == effective_action_key)
    if start_date:
        base = base.where(CreditLog.created_at >= start_date)
    if end_date:
        base = base.where(CreditLog.created_at <= end_date)

    # total count
    count_q = select(func.count()).select_from(base.subquery())
    total = (await db.execute(count_q)).scalar_one()

    # paged rows
    rows_q = (
        base.order_by(CreditLog.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    logs = (await db.execute(rows_q)).scalars().all()

    # Derive a friendly log_type for each row
    def _credit_log_type(ak: str) -> str:
        if ak == ACTION_IMAGE_GENERATION:
            return "image"
        if ak == ACTION_VIDEO_GENERATION:
            return "video"
        if ak == ACTION_CAPTION_GENERATION:
            return "caption"
        return ak

    items = [
        {
            **_log_to_dict(l),
            "log_type": _credit_log_type(l.action_key),
        }
        for l in logs
    ]

    return _ok({
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    })


@router.get("/logs/{log_id}")
async def get_log(
    log_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a single credit log owned by the current user."""
    result = await db.execute(
        select(CreditLog).where(CreditLog.id == log_id, CreditLog.user_id == user.id)
    )
    log = result.scalar_one_or_none()
    if not log:
        return _err("Log not found", http=404)
    return _ok(_log_to_dict(log))


@router.post("/logs")
async def create_log(
    payload: CreditLogCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a credit log entry.

    The `credits_used` value is looked up from the CreditRate table by
    `action_key`. If no active rate exists the request is rejected.
    """
    rate_result = await db.execute(
        select(CreditRate).where(CreditRate.action_key == payload.action_key)
    )
    rate = rate_result.scalar_one_or_none()
    if not rate:
        return _err(
            f"No credit rate configured for action '{payload.action_key}'",
            http=404,
        )
    if not rate.is_active:
        return _err(f"Action '{payload.action_key}' is disabled", http=400)

    log = CreditLog(
        user_id=user.id,
        action_key=payload.action_key,
        credits_used=rate.credits,  # ← pulled from the rate table
        reference_type=payload.reference_type,
        reference_id=payload.reference_id,
        meta=payload.meta,
        note=payload.note,
    )
    db.add(log)
    await db.flush()
    await db.refresh(log)
    return _ok(_log_to_dict(log), message="Credit logged", http=201), 201


@router.get("/summary")
async def usage_summary(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Aggregate credit usage for the current user (total + per action).

    Returns counts broken down by the four log types:
    - post    → number of PostLog rows
    - image   → credits used for image_generation
    - video   → credits used for video_generation
    - caption → credits used for caption_generation
    """
    # Credit usage by action_key
    rows = await db.execute(
        select(CreditLog.action_key, func.sum(CreditLog.credits_used))
        .where(CreditLog.user_id == user.id)
        .group_by(CreditLog.action_key)
    )
    by_action: dict[str, int] = {}
    total = 0
    for action_key, used in rows.all():
        used = int(used or 0)
        by_action[action_key] = used
        total += used

    # PostLog count (post lifecycle events)
    post_count = (await db.execute(
        select(func.count()).select_from(
            select(PostLog).where(PostLog.user_id == user.id).subquery()
        )
    )).scalar_one()

    # Build a by_log_type summary
    by_log_type: dict[str, dict] = {
        "post": {"count": int(post_count or 0), "credits_used": 0},
        "image": {"count": 0, "credits_used": by_action.get(ACTION_IMAGE_GENERATION, 0)},
        "video": {"count": 0, "credits_used": by_action.get(ACTION_VIDEO_GENERATION, 0)},
        "caption": {"count": 0, "credits_used": by_action.get(ACTION_CAPTION_GENERATION, 0)},
    }

    # Fill in counts for credit-based log types
    for ak, lt in [
        (ACTION_IMAGE_GENERATION, "image"),
        (ACTION_VIDEO_GENERATION, "video"),
        (ACTION_CAPTION_GENERATION, "caption"),
    ]:
        cnt = (await db.execute(
            select(func.count()).select_from(
                select(CreditLog).where(
                    CreditLog.user_id == user.id,
                    CreditLog.action_key == ak,
                ).subquery()
            )
        )).scalar_one()
        by_log_type[lt]["count"] = int(cnt or 0)

    return _ok({
        "total_used": total,
        "by_action": by_action,
        "by_log_type": by_log_type,
    })


# ── Unified all-logs endpoint ────────────────────────────────────────

@router.get("/all-logs")
async def list_all_logs(
    log_type: str | None = Query(None, description="Filter by log type: post / image / video / caption"),
    start_date: datetime | None = Query(None, description="ISO datetime lower bound"),
    end_date: datetime | None = Query(None, description="ISO datetime upper bound"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Unified logs endpoint — merges PostLog + CreditLog into one feed.

    Each item has a ``log_type`` field:
    - ``post``    → from PostLog (post lifecycle: created/scheduled/regenerated/deleted)
    - ``image``   → from CreditLog (action_key=image_generation)
    - ``video``   → from CreditLog (action_key=video_generation)
    - ``caption`` → from CreditLog (action_key=caption_generation)

    Filter with ``?log_type=post`` / ``?log_type=image`` etc.
    If ``log_type`` is omitted, all four types are merged (sorted by created_at desc).
    """
    credit_items: list[dict] = []
    post_items: list[dict] = []

    # ── Determine which types to fetch ───────────────────────────────
    fetch_post = log_type is None or log_type == "post"
    fetch_credit = log_type is None or log_type in LOG_TYPE_TO_ACTION_KEY

    # ── Fetch CreditLog rows ─────────────────────────────────────────
    if fetch_credit:
        credit_base = select(CreditLog).where(CreditLog.user_id == user.id)
        if log_type and log_type in LOG_TYPE_TO_ACTION_KEY:
            credit_base = credit_base.where(
                CreditLog.action_key == LOG_TYPE_TO_ACTION_KEY[log_type]
            )
        if start_date:
            credit_base = credit_base.where(CreditLog.created_at >= start_date)
        if end_date:
            credit_base = credit_base.where(CreditLog.created_at <= end_date)

        credit_rows = (await db.execute(
            credit_base.order_by(CreditLog.created_at.desc())
        )).scalars().all()

        def _credit_log_type(ak: str) -> str:
            if ak == ACTION_IMAGE_GENERATION:
                return "image"
            if ak == ACTION_VIDEO_GENERATION:
                return "video"
            if ak == ACTION_CAPTION_GENERATION:
                return "caption"
            return ak

        credit_items = [
            {
                **_log_to_dict(l),
                "log_type": _credit_log_type(l.action_key),
            }
            for l in credit_rows
        ]

    # ── Fetch PostLog rows ───────────────────────────────────────────
    if fetch_post:
        post_base = select(PostLog).where(PostLog.user_id == user.id)
        if start_date:
            post_base = post_base.where(PostLog.created_at >= start_date)
        if end_date:
            post_base = post_base.where(PostLog.created_at <= end_date)

        post_rows = (await db.execute(
            post_base.order_by(PostLog.created_at.desc())
        )).scalars().all()

        post_items = [
            {
                "id": log.id,
                "user_id": log.user_id,
                "log_type": "post",
                "action": log.action,
                "post_id": log.post_id,
                "platform": log.platform,
                "day_group_id": log.day_group_id,
                "credits_used": 0,
                "reference_type": "post",
                "reference_id": log.post_id,
                "meta": log.meta,
                "note": log.note or "",
                "created_at": log.created_at.isoformat() if log.created_at else None,
            }
            for log in post_rows
        ]

    # ── Merge + sort by created_at desc ──────────────────────────────
    all_items = credit_items + post_items
    all_items.sort(key=lambda x: x.get("created_at") or "", reverse=True)

    total = len(all_items)
    start = (page - 1) * page_size
    end = start + page_size
    paged = all_items[start:end]

    return _ok({
        "items": paged,
        "total": total,
        "page": page,
        "page_size": page_size,
    })
