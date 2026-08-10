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
from src.schemas.credits import (
    CreditRateCreate, CreditRateUpdate, CreditRateOut,
    CreditLogCreate, CreditLogOut, CreditLogListOut, CreditUsageSummary,
)

router = APIRouter(prefix="/api/credits", tags=["credits"])


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
    action_key: str | None = Query(None, description="Filter by action_key"),
    start_date: datetime | None = Query(None, description="ISO datetime lower bound"),
    end_date: datetime | None = Query(None, description="ISO datetime upper bound"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List the current user's credit logs (paginated, filterable)."""
    base = select(CreditLog).where(CreditLog.user_id == user.id)

    if action_key:
        base = base.where(CreditLog.action_key == action_key)
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

    return _ok({
        "items": [_log_to_dict(l) for l in logs],
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
    """Aggregate credit usage for the current user (total + per action)."""
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

    return _ok({"total_used": total, "by_action": by_action})
