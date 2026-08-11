"""Posts router — list, create-post wizard, bulk-create, day-group."""
import json
import re
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Request, Query
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.database import get_db
from src.dependencies.auth import get_current_user
from src.models.accounts import User
from src.models.posts import Post
from src.models.post_media import PostMedia
from src.models.assets import Asset
from src.models.content_plans import UserAIKey
from src.models.credits import CreditRate, CreditLog
from src.models.credits import (
    ACTION_IMAGE_GENERATION, ACTION_VIDEO_GENERATION,
    ACTION_CAPTION_GENERATION,
)
from src.services.crypto import decrypt
from src.services.credits import log_credit_async
from src.services.zettalgor import (
    ZettalgorError,
    enhance_description, generate_batch_captions, regenerate_single_caption,
)
from src.services.images import generate_content_image, GeminiError
from src.services.videos import generate_content_video, VideoGenerationError
from src.schemas.posts import (
    EnhanceDescriptionRequest, GenerateCaptionsRequest, RegenerateCaptionRequest,
    RegenerateImageRequest, RegenerateDayGroupRequest,
    FinalSubmitRequest,
    RegenerateVideoRequest,
    UpdateDayGroupScheduleRequest,
    PLATFORM_ALIASES,
)

router = APIRouter(prefix="/posts", tags=["posts"])

# ── Create-Post wizard helpers ──────────────────────────────────────────
# NOTE: this must follow Python's datetime.weekday() convention
# (Mon=0, Tue=1, ..., Sun=6) — NOT the JS/Django Sunday=0 convention.
# A previous version used Sun=0 which mislabelled every day and caused
# "No valid dates in the given range with the selected active days".
DAY_NAME_MAP = {0: "Mon", 1: "Tue", 2: "Wed", 3: "Thu", 4: "Fri", 5: "Sat", 6: "Sun"}
MAX_RANGE_DAYS = 21


async def _record_ai_asset(
    db: AsyncSession,
    user_id: int,
    path: str,
    prompt: str = "",
    model: str = "",
    mime_type: str = "image/png",
) -> None:
    """Create an Asset row (source='ai') for a generated image.

    Best-effort: never raises — asset tracking must not break post
    generation. The binary already lives on disk under MEDIA_DIR; we
    only record its metadata so it shows up in `GET /api/assets/?source=ai`.
    """
    try:
        rel = path
        # `path` from generate_content_image is already relative to MEDIA_DIR.
        full = settings.MEDIA_DIR / rel
        size = full.stat().st_size if full.is_file() else None
        name = Path(rel).name
        asset = Asset(
            user_id=user_id,
            name=name[:255],
            description=prompt[:2000] if prompt else "",
            asset_type="image",
            file=rel,
            mime_type=mime_type,
            file_size=size,
            source="ai",
            meta={"model": model} if model else None,
        )
        db.add(asset)
        await db.flush()
    except Exception as exc:
        print(f"[ai-asset] WARN: failed to record AI asset: {exc}", flush=True)


def _compute_scheduled_dates(
    from_date: str,
    to_date: str,
    active_days: list[str] | None = None,
    tz_name: str = "UTC",
) -> list[datetime]:
    """Compute the per-day scheduled datetimes from a from/to range.

    Mirrors the frontend logic in CreatePost.jsx:
    - Walk every calendar day from from_date's day to to_date's day.
    - Keep only days whose weekday name is in active_days (empty = all days).
    - Cap at MAX_RANGE_DAYS (21).
    - First day gets the from_date time, last day gets the to_date time,
      middle days get an evenly-spaced time between them.
    """
    try:
        local_tz = ZoneInfo(tz_name)
    except Exception:
        local_tz = ZoneInfo(settings.CELERY_TIMEZONE)

    def _parse(value: str) -> datetime:
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=local_tz)
        return dt

    # Convert to the user's LOCAL timezone BEFORE walking days. The frontend
    # sends UTC ISO strings (`.toISOString()`), so without this conversion a
    # positive-offset user (e.g. Asia/Kolkata +5:30) picking "Tue" would have
    # cur.weekday() return "Mon" at UTC midnight — which then fails the
    # active_days filter ("No valid dates in the given range..."). Converting
    # here also makes start.hour/start.minute reflect the LOCAL time the user
    # actually picked, not the UTC hour.
    start = _parse(from_date).astimezone(local_tz)
    end = _parse(to_date).astimezone(local_tz)
    active = [d.strip().capitalize()[:3] for d in (active_days or []) if d.strip()]

    # Walk day-by-day from start date to end date (inclusive)
    dates: list[datetime] = []
    cur = start.replace(hour=0, minute=0, second=0, microsecond=0)
    end_day = end.replace(hour=0, minute=0, second=0, microsecond=0)
    while cur <= end_day:
        day_name = DAY_NAME_MAP.get(cur.weekday(), "")
        if not active or day_name in active:
            dates.append(cur)
        cur = cur + timedelta(days=1)

    dates = dates[:MAX_RANGE_DAYS]
    if not dates:
        return dates

    from_time = {"hour": start.hour, "minute": start.minute}
    to_time = {"hour": end.hour, "minute": end.minute}

    if len(dates) == 1:
        dates[0] = dates[0].replace(hour=from_time["hour"], minute=from_time["minute"])
    else:
        dates[0] = dates[0].replace(hour=from_time["hour"], minute=from_time["minute"])
        dates[-1] = dates[-1].replace(hour=to_time["hour"], minute=to_time["minute"])
        total_from = from_time["hour"] * 60 + from_time["minute"]
        total_to = to_time["hour"] * 60 + to_time["minute"]
        for i in range(1, len(dates) - 1):
            ratio = i / (len(dates) - 1)
            interp = round(total_from + ratio * (total_to - total_from))
            dates[i] = dates[i].replace(hour=interp // 60, minute=interp % 60)

    return dates


@router.get("/list/")
async def list_posts(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    status: str | None = Query(None, description="Filter by status (pending/scheduled/posted/failed)"),
    platform: str | None = Query(None, description="Filter by platform"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List the current user's posts with pagination + optional filters."""
    base = select(Post).options(selectinload(Post.media_files)).where(Post.user_id == user.id)

    if status:
        base = base.where(Post.status == status)
    if platform:
        base = base.where(Post.platform == platform)

    # Total count (for pagination metadata)
    count_base = select(Post.id).where(Post.user_id == user.id)
    if status:
        count_base = count_base.where(Post.status == status)
    if platform:
        count_base = count_base.where(Post.platform == platform)
    total = (await db.execute(select(func.count()).select_from(count_base.subquery()))).scalar_one()

    # Paginated rows (newest first)
    rows_q = base.order_by(Post.id.desc()).offset((page - 1) * page_size).limit(page_size)
    posts = (await db.execute(rows_q)).scalars().all()

    post_data = []
    for post in posts:
        media_urls = [
            f"{settings.BASE_URL}{settings.MEDIA_URL_PREFIX}/{m.file}"
            for m in post.media_files
        ]
        post_data.append({
            "id": post.id,
            "user_id": post.user_id,
            "caption": post.caption,
            "media": media_urls,
            "platform": post.platform,
            "scheduled_time": post.scheduled_time.isoformat() if post.scheduled_time else None,
            "status": post.status,
            "post_url": post.post_url,
        })

    return {
        "success": True,
        "message": "Posts fetched successfully",
        "data": post_data,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": (total + page_size - 1) // page_size,
            "has_next": page * page_size < total,
            "has_prev": page > 1,
        },
    }


@router.get("/scheduled/")
async def list_scheduled_posts(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    platform: str | None = Query(None, description="Filter by platform"),
    upcoming_only: bool = Query(True, description="Only posts scheduled in the future"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List the current user's scheduled posts (sorted by scheduled_time ascending).

    Returns posts with status=scheduled, optionally filtered to only
    upcoming (future) scheduled times.
    """
    now = datetime.now(timezone.utc)
    base = select(Post).options(selectinload(Post.media_files)).where(
        Post.user_id == user.id,
        Post.status == Post.STATUS_SCHEDULED,
    )
    count_base = select(Post.id).where(
        Post.user_id == user.id,
        Post.status == Post.STATUS_SCHEDULED,
    )

    if upcoming_only:
        base = base.where(Post.scheduled_time >= now)
        count_base = count_base.where(Post.scheduled_time >= now)

    if platform:
        base = base.where(Post.platform == platform)
        count_base = count_base.where(Post.platform == platform)

    total = (await db.execute(select(func.count()).select_from(count_base.subquery()))).scalar_one()

    # Sort by scheduled_time ascending (soonest first)
    rows_q = base.order_by(Post.scheduled_time.asc()).offset((page - 1) * page_size).limit(page_size)
    posts = (await db.execute(rows_q)).scalars().all()

    post_data = []
    for post in posts:
        media_urls = [
            f"{settings.BASE_URL}{settings.MEDIA_URL_PREFIX}/{m.file}"
            for m in post.media_files
        ]
        post_data.append({
            "id": post.id,
            "user_id": post.user_id,
            "caption": post.caption,
            "media": media_urls,
            "platform": post.platform,
            "scheduled_time": post.scheduled_time.isoformat() if post.scheduled_time else None,
            "status": post.status,
            "post_url": post.post_url,
            "day_group_id": post.day_group_id,
        })

    return {
        "success": True,
        "message": "Scheduled posts fetched successfully",
        "data": post_data,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": (total + page_size - 1) // page_size,
            "has_next": page * page_size < total,
            "has_prev": page > 1,
        },
    }


@router.get("/upcoming/summary/")
async def upcoming_summary(
    days_ahead: int = Query(7, ge=1, le=90, description="How many days ahead to look"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Dashboard summary of upcoming scheduled posts.

    Returns:
      - total_scheduled: count of scheduled posts in the next `days_ahead` days
      - by_platform: {platform: count}
      - by_date: [{date, count, platforms: [{platform, count}]}]
      - next_post: the soonest upcoming post (or null)
      - pending_count: posts still pending (not yet scheduled)
    """
    now = datetime.now(timezone.utc)
    horizon = now + timedelta(days=days_ahead)

    # All scheduled posts within the window
    rows = (await db.execute(
        select(Post).options(selectinload(Post.media_files))
        .where(
            Post.user_id == user.id,
            Post.status == Post.STATUS_SCHEDULED,
            Post.scheduled_time >= now,
            Post.scheduled_time <= horizon,
        )
        .order_by(Post.scheduled_time.asc())
    )).scalars().all()

    # Pending count (not yet scheduled)
    pending_count = (await db.execute(
        select(func.count(Post.id)).where(
            Post.user_id == user.id,
            Post.status == Post.STATUS_PENDING,
        )
    )).scalar_one()

    # Group by platform
    by_platform: dict[str, int] = {}
    for p in rows:
        by_platform[p.platform] = by_platform.get(p.platform, 0) + 1

    # Group by date (YYYY-MM-DD)
    by_date_map: dict[str, dict] = {}
    for p in rows:
        day_key = p.scheduled_time.strftime("%Y-%m-%d") if p.scheduled_time else "unknown"
        if day_key not in by_date_map:
            by_date_map[day_key] = {"date": day_key, "count": 0, "platforms": {}}
        entry = by_date_map[day_key]
        entry["count"] += 1
        entry["platforms"][p.platform] = entry["platforms"].get(p.platform, 0) + 1

    by_date = []
    for day_key in sorted(by_date_map.keys()):
        entry = by_date_map[day_key]
        by_date.append({
            "date": entry["date"],
            "count": entry["count"],
            "platforms": [
                {"platform": plat, "count": cnt}
                for plat, cnt in sorted(entry["platforms"].items())
            ],
        })

    # Next upcoming post
    next_post = None
    if rows:
        p = rows[0]
        media_urls = [
            f"{settings.BASE_URL}{settings.MEDIA_URL_PREFIX}/{m.file}"
            for m in p.media_files
        ]
        next_post = {
            "id": p.id,
            "caption": p.caption,
            "media": media_urls,
            "platform": p.platform,
            "scheduled_time": p.scheduled_time.isoformat() if p.scheduled_time else None,
            "day_group_id": p.day_group_id,
        }

    return {
        "success": True,
        "message": "Upcoming summary fetched",
        "data": {
            "total_scheduled": len(rows),
            "pending_count": pending_count,
            "by_platform": by_platform,
            "by_date": by_date,
            "next_post": next_post,
            "window": {
                "from": now.isoformat(),
                "to": horizon.isoformat(),
                "days_ahead": days_ahead,
            },
        },
    }


@router.delete("/{post_id}/")
async def delete_post(
    post_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a post owned by the logged-in user.

    Also deletes the associated media files from disk.
    Cannot delete a post that is currently being processed by the agent.
    """
    result = await db.execute(
        select(Post).options(selectinload(Post.media_files))
        .where(Post.id == post_id, Post.user_id == user.id)
    )
    post = result.scalar_one_or_none()

    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    if post.status == Post.STATUS_PROCESSING:
        raise HTTPException(
            status_code=400,
            detail="Cannot delete a post that is currently being processed",
        )

    # Delete media files from disk
    import os
    for media in post.media_files:
        media_path = settings.MEDIA_DIR / media.file
        if media_path.exists():
            try:
                os.remove(media_path)
            except Exception:
                pass

    # Delete the post (cascade deletes PostMedia rows)
    await db.delete(post)
    await db.commit()

    return {"success": True, "message": "Post deleted successfully"}


@router.delete("/user/{user_id}/all/")
async def delete_all_posts_for_user(
    user_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete ALL posts for a specific user_id.

    Admin/maintenance endpoint — deletes every post owned by the given
    user_id, including media files on disk. Posts currently being processed
    by the agent are skipped (not deleted) to avoid corrupting active tasks.
    """
    # Only allow the user themselves or any authenticated user (adjust
    # with an admin check here if needed).
    result = await db.execute(
        select(Post).options(selectinload(Post.media_files))
        .where(Post.user_id == user_id)
        .order_by(Post.id)
    )
    posts = result.scalars().all()

    if not posts:
        return {"success": True, "message": f"No posts found for user_id {user_id}", "deleted_count": 0}

    import os
    deleted_count = 0
    skipped_count = 0

    for post in posts:
        if post.status == Post.STATUS_PROCESSING:
            skipped_count += 1
            continue

        # Delete media files from disk
        for media in post.media_files:
            media_path = settings.MEDIA_DIR / media.file
            if media_path.exists():
                try:
                    os.remove(media_path)
                except Exception:
                    pass

        await db.delete(post)
        deleted_count += 1

    await db.commit()

    return {
        "success": True,
        "message": f"Deleted {deleted_count} post(s) for user_id {user_id}",
        "deleted_count": deleted_count,
        "skipped_count": skipped_count,
    }


@router.post("/schedule/")
async def schedule_single_post(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a single post scheduled for a specific time.

    Body:
        {
            "platform": "facebook",          # facebook/instagram/linkedin/x
            "caption": "Hello world!",
            "scheduled_time": "2026-08-07T15:35:00+05:30",  # ISO 8601
            "media": ["<url_or_path>"]         # optional
        }

    The post is created with status=scheduled so the auto-scheduler
    picks it up when the time arrives and dispatches it to the agent.
    """
    import uuid

    body = await request.json()
    platform = _normalize_platform(body.get("platform", ""))
    caption = body.get("caption", "")
    scheduled_time_str = body.get("scheduled_time")
    media_list = body.get("media", [])

    if not platform:
        raise HTTPException(status_code=400, detail="platform is required")
    if not caption:
        raise HTTPException(status_code=400, detail="caption is required")
    if not scheduled_time_str:
        raise HTTPException(status_code=400, detail="scheduled_time is required")

    # Parse and convert to UTC
    tz_name = body.get("timezone", "UTC")
    scheduled_time = _parse_scheduled_time(scheduled_time_str, tz_name)

    day_group_id = str(uuid.uuid4())

    post = Post(
        user_id=user.id,
        caption=caption,
        platform=platform,
        scheduled_time=scheduled_time,
        status=Post.STATUS_SCHEDULED,
        day_group_id=day_group_id,
    )
    db.add(post)
    await db.flush()

    # Attach media if provided
    for media_item in media_list:
        if media_item:
            db.add(PostMedia(post_id=post.id, file=media_item))

    await db.commit()

    return {
        "success": True,
        "message": "Post scheduled successfully",
        "data": {
            "post_id": post.id,
            "user_id": user.id,
            "platform": platform,
            "caption": caption,
            "scheduled_time": scheduled_time.isoformat(),
            "status": post.status,
            "day_group_id": day_group_id,
        },
    }


# ──────────────────────────────────────────────────────────────────────────
# Create-Post wizard endpoints (multi-stage frontend flow)
# ──────────────────────────────────────────────────────────────────────────

def _normalize_platform(p: str) -> str:
    """Map frontend platform values (twitter/tiktok/youtube) to backend ones."""
    return PLATFORM_ALIASES.get(p.lower(), p.lower())


def _parse_scheduled_time(value: str, tz_name: str = "UTC") -> datetime:
    """Parse an ISO datetime string and convert to UTC for storage.

    Naive datetimes are interpreted in the given IANA timezone.
    """
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        try:
            local_tz = ZoneInfo(tz_name)
        except Exception:
            local_tz = ZoneInfo(settings.CELERY_TIMEZONE)
        dt = dt.replace(tzinfo=local_tz)
    return dt.astimezone(timezone.utc)


@router.post("/enhance-description/")
async def enhance_description_endpoint(
    request: EnhanceDescriptionRequest,
    user: User = Depends(get_current_user),
):
    """Stage 1 — AI-enhance the user's free-form promotion description."""
    if not request.description or not request.description.strip():
        return {"success": False, "message": "description is required", "errors": {}}, 400

    try:
        result = enhance_description(
            description=request.description,
            website=request.website,
            title=request.title,
        )
        return {"success": True, "message": "Description enhanced", "data": result}
    except ZettalgorError as e:
        return {"success": False, "message": "Zettalgor API request failed", "errors": {"details": str(e)}}, 400
    except Exception as e:
        return {"success": False, "message": "Something went wrong", "errors": str(e)}, 400


@router.post("/generate-captions/")
async def generate_captions_endpoint(
    request: GenerateCaptionsRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Stage 3 — generate one caption per scheduled day AND create Post rows.

    Accepts ``from_date`` / ``to_date`` (the range the user picks in Stage 2)
    plus ``active_days`` (e.g. ``["Mon","Wed","Fri"]``). The backend computes
    the per-day scheduled datetimes itself — same logic as the frontend.

    For each computed day, one Post is created per platform (status=pending),
    so every generated caption is tied to a real post row with a post_id.
    Returns the full post details for each created post.
    """
    if not request.description or not request.description.strip():
        return {"success": False, "message": "description is required", "errors": {}}, 400
    if not request.from_date or not request.to_date:
        return {"success": False, "message": "from_date and to_date are required", "errors": {}}, 400
    if not request.platforms:
        return {"success": False, "message": "platforms is required", "errors": {}}, 400

    scheduled_dates = _compute_scheduled_dates(
        from_date=request.from_date,
        to_date=request.to_date,
        active_days=request.active_days,
        tz_name=request.timezone,
    )
    if not scheduled_dates:
        return {"success": False, "message": "No valid dates in the given range with the selected active days", "errors": {}}, 400

    scheduled_dates_iso = [d.isoformat() for d in scheduled_dates]

    try:
        items = generate_batch_captions(
            description=request.description,
            platforms=request.platforms,
            scheduled_dates=scheduled_dates_iso,
            timezone=request.timezone,
            website=request.website,
            title=request.title,
        )
    except ZettalgorError as e:
        return {"success": False, "message": "Zettalgor API request failed", "errors": {"details": str(e)}}, 400
    except Exception as e:
        return {"success": False, "message": "Something went wrong", "errors": str(e)}, 400

    # Check if image generation is needed
    has_image = "image" in (request.post_types or [])
    has_video = "video" in (request.post_types or [])
    needs_media = has_image or has_video
    print(f"[generate-captions] DEBUG: has_image={has_image}, has_video={has_video}, post_types={request.post_types}", flush=True)
    gemini_api_key = None
    gemini_record = None
    if needs_media:
        print(f"[generate-captions] DEBUG: loading Gemini key for user {user.id}", flush=True)
        gemini_api_key, gemini_record = await _load_gemini_key(db, user)
        print(f"[generate-captions] DEBUG: gemini_api_key={'loaded' if gemini_api_key else 'None'}, record={'yes' if gemini_record else 'no'}", flush=True)
        if gemini_record:
            print(f"[generate-captions] DEBUG: default_image_model={gemini_record.default_image_model}, last4={gemini_record.gemini_key_last4}", flush=True)

    # Create one Post per day per platform (status=pending, not yet scheduled)
    created_posts = []
    day_groups = []  # [{day, day_group_id, scheduled_time, posts: [post_id,...]}]
    generation_errors = []  # collected per-day generation failures for the response
    for i, day_dt in enumerate(scheduled_dates):
        caption_item = items[i] if i < len(items) else None
        caption_text = ""
        if caption_item:
            caption_text = caption_item.get("content", "")
            hashtags = caption_item.get("hashtags", "")
            if hashtags:
                caption_text = f"{caption_text}\n\n{hashtags}"

        day_errors = {}  # per-day errors: {"image": "...", "video": "..."}

        # Generate image for this day if image post type is selected
        image_url = ""
        image_path = ""
        if has_image and not gemini_api_key:
            day_errors["image"] = "No Gemini API key configured. Save one via POST /api/ai-keys/gemini/"
            print(f"[generate-captions] DEBUG: day {i} - SKIPPED image (no Gemini key)", flush=True)
        if has_image and gemini_api_key:
            image_model = (gemini_record.default_image_model if gemini_record else "") or settings.GEMINI_IMAGE_MODEL
            image_platform = _normalize_platform(request.platforms[0]) if request.platforms else "instagram"
            print(f"[generate-captions] DEBUG: day {i} - generating image, model={image_model}, platform={image_platform}", flush=True)
            try:
                gen = generate_content_image(
                    api_key=gemini_api_key,
                    text=request.description,
                    platform=image_platform,
                    brand_summary="",
                    model=image_model,
                    prompt_override="",
                )
                image_path = gen["path"]
                print(f"[generate-captions] DEBUG: day {i} - image generated OK, path={image_path}", flush=True)
                # Record the generated image as an AI asset (best-effort).
                await _record_ai_asset(db, user.id, image_path, model=image_model)
            except GeminiError as e:
                day_errors["image"] = f"Image generation failed: {e}"
                print(f"[generate-captions] DEBUG: day {i} - GeminiError: {e}", flush=True)
            except Exception as e:
                day_errors["image"] = f"Image generation failed: {type(e).__name__}: {e}"
                print(f"[generate-captions] DEBUG: day {i} - Exception: {e}", flush=True)

        # Generate video for this day if video post type is selected
        video_url = ""
        video_path = ""
        if has_video and not gemini_api_key:
            day_errors["video"] = "No Gemini API key configured. Save one via POST /api/ai-keys/gemini/"
            print(f"[generate-captions] DEBUG: day {i} - SKIPPED video (no Gemini key)", flush=True)
        if has_video and gemini_api_key:
            video_model = (gemini_record.default_video_model if gemini_record else "") or settings.GEMINI_VIDEO_MODEL
            video_platform = _normalize_platform(request.platforms[0]) if request.platforms else "instagram"
            print(f"[generate-captions] DEBUG: day {i} - generating video, model={video_model}, platform={video_platform}", flush=True)
            try:
                vgen = generate_content_video(
                    api_key=gemini_api_key,
                    text=request.description,
                    platform=video_platform,
                    brand_summary="",
                    model=video_model,
                    prompt_override="",
                )
                video_path = vgen["path"]
                print(f"[generate-captions] DEBUG: day {i} - video generated OK, path={video_path}", flush=True)
            except VideoGenerationError as e:
                day_errors["video"] = f"Video generation failed: {e}"
                print(f"[generate-captions] DEBUG: day {i} - VideoGenerationError: {e}", flush=True)
            except Exception as e:
                day_errors["video"] = f"Video generation failed: {type(e).__name__}: {e}"
                print(f"[generate-captions] DEBUG: day {i} - video Exception: {e}", flush=True)

        if day_errors:
            generation_errors.append({"day": i, "errors": day_errors})

        # One UUID shared by all platform posts on this day
        day_group_id = str(uuid.uuid4())
        day_post_ids = []

        # Primary media on the Post row: video takes precedence over image
        # (both are also attached as PostMedia rows below).
        primary_media = video_path or image_path or None

        for platform in request.platforms:
            norm_platform = _normalize_platform(platform)
            post = Post(
                user_id=user.id,
                caption=caption_text,
                platform=norm_platform,
                scheduled_time=day_dt.astimezone(timezone.utc),
                status=Post.STATUS_PENDING,
                day_group_id=day_group_id,
                media=primary_media,
            )
            db.add(post)
            await db.flush()

            # Attach image / video as PostMedia rows if generated
            if image_path:
                db.add(PostMedia(post_id=post.id, file=image_path))
            if video_path:
                db.add(PostMedia(post_id=post.id, file=video_path))

            day_post_ids.append(post.id)
            created_posts.append({
                "post_id": post.id,
                "user_id": user.id,
                "day": i,
                "day_group_id": day_group_id,
                "platform": norm_platform,
                "caption": caption_text,
                "image_url": image_url,
                "video_url": video_url,
                "scheduled_time": day_dt.isoformat(),
                "status": post.status,
                "errors": day_errors or None,
            })

        # Build the media URLs for the response (use the first post's media)
        if image_path:
            image_url = f"{settings.BASE_URL}{settings.MEDIA_URL_PREFIX}/{image_path}"
            for cp in created_posts[-len(request.platforms):]:
                cp["image_url"] = image_url
        if video_path:
            video_url = f"{settings.BASE_URL}{settings.MEDIA_URL_PREFIX}/{video_path}"
            for cp in created_posts[-len(request.platforms):]:
                cp["video_url"] = video_url

        # ── Credit logging (once per day, not per platform) ───────────
        # Logged at the point of generation. Skips silently if no rate.
        if caption_item:
            await log_credit_async(
                db, user.id, ACTION_CAPTION_GENERATION,
                reference_type="post",
                reference_id=day_post_ids[0] if day_post_ids else None,
                meta={"day_group_id": day_group_id, "day": i},
                note="generate-captions caption",
            )
        if image_path:
            await log_credit_async(
                db, user.id, ACTION_IMAGE_GENERATION,
                reference_type="post",
                reference_id=day_post_ids[0] if day_post_ids else None,
                meta={"day_group_id": day_group_id, "day": i, "media": image_path},
                note="generate-captions image",
            )
        if video_path:
            await log_credit_async(
                db, user.id, ACTION_VIDEO_GENERATION,
                reference_type="post",
                reference_id=day_post_ids[0] if day_post_ids else None,
                meta={"day_group_id": day_group_id, "day": i, "media": video_path, "model": video_model if has_video and gemini_api_key else ""},
                note="generate-captions video",
            )

        # Enrich the AI-generated item with the post IDs + day_group_id + media
        if i < len(items):
            items[i]["day_group_id"] = day_group_id
            items[i]["post_ids"] = day_post_ids
            items[i]["image_url"] = image_url
            items[i]["video_url"] = video_url
            items[i]["errors"] = day_errors or None

        day_groups.append({
            "day": i,
            "day_group_id": day_group_id,
            "scheduled_time": day_dt.isoformat(),
            "post_ids": day_post_ids,
        })

    return {
        "success": True,
        "message": f"{len(created_posts)} post(s) created with AI captions",
        "data": {
            "items": items,
            "posts": created_posts,
            "day_groups": day_groups,
            "total_posts": len(created_posts),
            "total_days": len(day_groups),
            "errors": generation_errors or None,
        },
    }


@router.get("/day-group/{day_group_id}/")
async def get_posts_by_day_group(
    day_group_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get all posts for a single day (across all platforms) by day_group_id."""
    result = await db.execute(
        select(Post)
        .options(selectinload(Post.media_files))
        .where(Post.day_group_id == day_group_id, Post.user_id == user.id)
        .order_by(Post.platform)
    )
    posts = result.scalars().all()
    if not posts:
        return {"success": False, "message": "No posts found for this day_group_id"}, 404

    post_data = []
    for post in posts:
        media_urls = [
            f"{settings.BASE_URL}{settings.MEDIA_URL_PREFIX}/{m.file}"
            for m in post.media_files
        ]
        post_data.append({
            "post_id": post.id,
            "user_id": post.user_id,
            "day_group_id": post.day_group_id,
            "platform": post.platform,
            "caption": post.caption,
            "media": media_urls,
            "scheduled_time": post.scheduled_time.isoformat() if post.scheduled_time else None,
            "status": post.status,
            "post_url": post.post_url,
            "error_message": post.error_message,
        })

    return {
        "success": True,
        "message": f"{len(post_data)} post(s) found for this day",
        "data": {
            "day_group_id": day_group_id,
            "scheduled_time": posts[0].scheduled_time.isoformat() if posts[0].scheduled_time else None,
            "total_posts": len(post_data),
            "posts": post_data,
        },
    }


@router.post("/day-group/update-schedule/")
async def update_day_group_schedule(
    request: UpdateDayGroupScheduleRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Reschedule every post in a day group to a new date/time.

    - Parses ``scheduled_time`` the same way as the rest of the wizard:
      naive datetimes are interpreted in ``timezone`` (default UTC), then
      converted to UTC for storage.
    - Posts that are already ``posted`` are skipped (listed in ``skipped``)
      and left untouched. All other statuses (pending/scheduled/failed/...)
      are rescheduled.
    """
    if not request.day_group_id or not request.day_group_id.strip():
        return {"success": False, "message": "day_group_id is required", "errors": {}}, 400
    if not request.scheduled_time:
        return {"success": False, "message": "scheduled_time is required", "errors": {}}, 400

    # Parse the new scheduled time → UTC for storage.
    try:
        new_time = _parse_scheduled_time(request.scheduled_time, request.timezone)
    except ValueError as e:
        return {
            "success": False,
            "message": "Invalid scheduled_time (expected ISO datetime)",
            "errors": {"details": str(e)},
        }, 400

    # Load all posts for this day group belonging to the user.
    result = await db.execute(
        select(Post)
        .where(Post.day_group_id == request.day_group_id, Post.user_id == user.id)
        .order_by(Post.id)
    )
    posts = result.scalars().all()
    if not posts:
        return {"success": False, "message": "No posts found for this day_group_id", "errors": {}}, 404

    updated_posts = []
    skipped = []
    for post in posts:
        if post.status == Post.STATUS_POSTED:
            skipped.append({
                "post_id": post.id,
                "platform": post.platform,
                "status": post.status,
                "reason": "already posted",
            })
            continue
        post.scheduled_time = new_time
        await db.flush()
        updated_posts.append({
            "post_id": post.id,
            "user_id": post.user_id,
            "platform": post.platform,
            "scheduled_time": post.scheduled_time.isoformat() if post.scheduled_time else None,
            "status": post.status,
        })

    return {
        "success": True,
        "message": f"{len(updated_posts)} post(s) rescheduled"
                   + (f", {len(skipped)} skipped (already posted)" if skipped else ""),
        "data": {
            "day_group_id": request.day_group_id,
            "scheduled_time": new_time.isoformat(),
            "updated_count": len(updated_posts),
            "posts": updated_posts,
            "skipped": skipped,
        },
    }


@router.post("/regenerate-caption/")
async def regenerate_caption_endpoint(
    request: RegenerateCaptionRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Stage 3 — regenerate a single day's caption using an optional prompt.

    If ``post_id`` is provided, the existing Post row's caption is updated
    in the database and the updated post details are returned.
    """
    if not request.description or not request.description.strip():
        return {"success": False, "message": "description is required", "errors": {}}, 400

    # Load post first (if given) so we can update its caption after regen.
    # No regeneration limit — users can regenerate unlimited times.
    post_obj = None
    if request.post_id:
        res = await db.execute(
            select(Post).where(Post.id == request.post_id, Post.user_id == user.id)
        )
        post_obj = res.scalar_one_or_none()

    try:
        result = regenerate_single_caption(
            description=request.description,
            platform=_normalize_platform(request.platform),
            prompt=request.prompt,
            day=request.day,
            scheduled_at=request.scheduled_at,
            website=request.website,
            title=request.title,
        )
    except ZettalgorError as e:
        return {"success": False, "message": "Zettalgor API request failed", "errors": {"details": str(e)}}, 400
    except Exception as e:
        return {"success": False, "message": "Something went wrong", "errors": str(e)}, 400

    # Credit log for the caption generation (silent skip if no rate).
    await log_credit_async(
        db, user.id, ACTION_CAPTION_GENERATION,
        reference_type="post",
        reference_id=request.post_id,
        meta={"day": request.day, "prompt": request.prompt[:80]} if request.prompt else {"day": request.day},
        note="regenerate-caption",
    )

    # Update post caption + bump regen counter
    post_details = None
    if post_obj:
        caption_text = result.get("content", "")
        hashtags = result.get("hashtags", "")
        if hashtags:
            caption_text = f"{caption_text}\n\n{hashtags}"
        post_obj.caption = caption_text
        post_obj.caption_regen_count += 1
        await db.flush()
        post_details = {
            "post_id": post_obj.id,
            "user_id": post_obj.user_id,
            "caption": post_obj.caption,
            "platform": post_obj.platform,
            "scheduled_time": post_obj.scheduled_time.isoformat() if post_obj.scheduled_time else None,
            "status": post_obj.status,
            "caption_regen_count": post_obj.caption_regen_count,
        }

    return {
        "success": True,
        "message": "Caption regenerated",
        "data": {**result, "post": post_details},
    }


async def _load_gemini_key(db: AsyncSession, user: User):
    """Load + decrypt the caller's stored Gemini API key. Returns (api_key, record)."""
    print(f"[gemini-key] DEBUG: loading key for user {user.id}", flush=True)
    result = await db.execute(select(UserAIKey).where(UserAIKey.user_id == user.id))
    record = result.scalar_one_or_none()
    if not record:
        print(f"[gemini-key] DEBUG: no UserAIKey record found", flush=True)
        return None, None
    if not record.gemini_key_encrypted:
        print(f"[gemini-key] DEBUG: record exists but no encrypted key", flush=True)
        return None, None
    print(f"[gemini-key] DEBUG: record found, last4={record.gemini_key_last4}, model={record.default_image_model}", flush=True)
    try:
        key = decrypt(record.gemini_key_encrypted)
        print(f"[gemini-key] DEBUG: decrypted OK, length={len(key)}", flush=True)
        return key, record
    except Exception as e:
        print(f"[gemini-key] DEBUG: decrypt failed: {e}", flush=True)
        return None, record


@router.post("/regenerate-image/")
async def regenerate_image_endpoint(
    request: RegenerateImageRequest,
    http_request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Stage 4 — regenerate a single day's image using an optional prompt."""
    if not request.description or not request.description.strip():
        return {"success": False, "message": "description is required", "errors": {}}, 400

    # Load post first (if given) so we can attach the regenerated image.
    # No regeneration limit — users can regenerate unlimited times.
    post_obj = None
    if request.post_id:
        res = await db.execute(
            select(Post).where(Post.id == request.post_id, Post.user_id == user.id)
        )
        post_obj = res.scalar_one_or_none()

    api_key, record = await _load_gemini_key(db, user)
    if not api_key:
        return {
            "success": False,
            "message": "No Gemini API key configured. Save one via POST /api/ai-keys/gemini/",
            "errors": {},
        }, 400

    model = request.model or (record.default_image_model if record else "") or settings.GEMINI_IMAGE_MODEL
    platform = _normalize_platform(request.platform)

    try:
        gen = generate_content_image(
            api_key=api_key,
            text=request.description,
            platform=platform,
            brand_summary=request.brand_summary,
            model=model,
            prompt_override=request.prompt,
        )
    except GeminiError as e:
        return {"success": False, "message": "Image generation failed", "errors": {"details": str(e)}}, 400
    except Exception as e:
        return {"success": False, "message": "Something went wrong", "errors": str(e)}, 400

    image_url = f"{settings.BASE_URL}{settings.MEDIA_URL_PREFIX}/{gen['path']}"

    # Record the generated image as an AI asset (best-effort).
    await _record_ai_asset(db, user.id, gen["path"], prompt=gen.get("prompt", ""), model=model)

    # Credit log for the image generation (silent skip if no rate).
    await log_credit_async(
        db, user.id, ACTION_IMAGE_GENERATION,
        reference_type="post",
        reference_id=request.post_id,
        meta={"day": request.day, "model": model, "media": gen["path"]},
        note="regenerate-image",
    )

    # If a post_id is given, attach the generated image to that post
    post_details = None
    if post_obj:
        # Save the generated image path as the post's media
        post_obj.media = gen['path']
        post_obj.image_regen_count += 1
        db.add(PostMedia(post_id=post_obj.id, file=gen['path']))
        await db.flush()
        post_details = {
            "post_id": post_obj.id,
            "user_id": post_obj.user_id,
            "platform": post_obj.platform,
            "caption": post_obj.caption,
            "media": [image_url],
            "scheduled_time": post_obj.scheduled_time.isoformat() if post_obj.scheduled_time else None,
            "status": post_obj.status,
            "image_regen_count": post_obj.image_regen_count,
        }

    return {
        "success": True,
        "message": "Image regenerated" + (" and attached to post" if post_details else ""),
        "data": {"image_url": image_url, "prompt": gen["prompt"], "post": post_details},
    }


@router.post("/regenerate-video/")
async def regenerate_video_endpoint(
    request: RegenerateVideoRequest,
    http_request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Stage 4 — regenerate a single day's video using an optional prompt.

    NOTE: Veo video generation is a long-running operation and may take
    several minutes. The request will block until the video is ready.
    """
    if not request.description or not request.description.strip():
        return {"success": False, "message": "description is required", "errors": {}}, 400

    # Load post first (if given) so we can attach the regenerated video.
    # No regeneration limit — users can regenerate unlimited times.
    post_obj = None
    if request.post_id:
        res = await db.execute(
            select(Post).where(Post.id == request.post_id, Post.user_id == user.id)
        )
        post_obj = res.scalar_one_or_none()

    api_key, record = await _load_gemini_key(db, user)
    if not api_key:
        return {
            "success": False,
            "message": "No Gemini API key configured. Save one via POST /api/ai-keys/gemini/",
            "errors": {},
        }, 400

    model = request.model or (record.default_video_model if record else "") or settings.GEMINI_VIDEO_MODEL
    platform = _normalize_platform(request.platform)

    try:
        gen = generate_content_video(
            api_key=api_key,
            text=request.description,
            platform=platform,
            brand_summary=request.brand_summary,
            model=model,
            prompt_override=request.prompt,
        )
    except VideoGenerationError as e:
        return {"success": False, "message": "Video generation failed", "errors": {"details": str(e)}}, 400
    except Exception as e:
        return {"success": False, "message": "Something went wrong", "errors": str(e)}, 400

    video_url = f"{settings.BASE_URL}{settings.MEDIA_URL_PREFIX}/{gen['path']}"

    # Credit log for the video generation (silent skip if no rate).
    await log_credit_async(
        db, user.id, ACTION_VIDEO_GENERATION,
        reference_type="post",
        reference_id=request.post_id,
        meta={"day": request.day, "model": model, "media": gen["path"]},
        note="regenerate-video",
    )

    # If a post_id is given, attach the generated video to that post
    post_details = None
    if post_obj:
        # Save the generated video path as the post's media
        post_obj.media = gen['path']
        post_obj.video_regen_count += 1
        db.add(PostMedia(post_id=post_obj.id, file=gen['path']))
        await db.flush()
        post_details = {
            "post_id": post_obj.id,
            "user_id": post_obj.user_id,
            "platform": post_obj.platform,
            "caption": post_obj.caption,
            "media": [video_url],
            "scheduled_time": post_obj.scheduled_time.isoformat() if post_obj.scheduled_time else None,
            "status": post_obj.status,
            "video_regen_count": post_obj.video_regen_count,
        }

    return {
        "success": True,
        "message": "Video regenerated" + (" and attached to post" if post_details else ""),
        "data": {"video_url": video_url, "prompt": gen["prompt"], "post": post_details},
    }


@router.post("/regenerate-day-group/")
async def regenerate_day_group_endpoint(
    request: RegenerateDayGroupRequest,
    http_request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Regenerate caption and/or image/video for every post in a day group.

    Mirrors the response shape of ``POST /posts/generate-captions/``.
    Only updates the parts requested in ``post_types``:
      - "content" -> regenerate caption
      - "image"   -> regenerate image
      - "video"   -> regenerate video
    """
    if not request.description or not request.description.strip():
        return {"success": False, "message": "description is required", "errors": {}}, 400
    if not request.day_group_id or not request.day_group_id.strip():
        return {"success": False, "message": "day_group_id is required", "errors": {}}, 400

    # Load all posts for this day group belonging to the user
    result = await db.execute(
        select(Post)
        .where(Post.day_group_id == request.day_group_id, Post.user_id == user.id)
        .order_by(Post.id)
    )
    posts = result.scalars().all()
    if not posts:
        return {"success": False, "message": "No posts found for this day_group_id", "errors": {}}, 404

    post_types = request.post_types or ["content"]
    update_caption = "content" in post_types
    update_image = "image" in post_types
    update_video = "video" in post_types

    # No regeneration limit — users can regenerate captions/images/videos
    # unlimited times. (Counter columns still track usage for analytics.)

    # Regenerate caption if requested (single caption shared across the day group)
    caption_text = ""
    hashtags = ""
    if update_caption:
        try:
            regenerated = regenerate_single_caption(
                description=request.description,
                platform=_normalize_platform(request.platform),
                prompt=request.prompt,
                day=request.day,
                scheduled_at=request.scheduled_at,
                website=request.website,
                title=request.title,
            )
        except ZettalgorError as e:
            return {"success": False, "message": "Zettalgor API request failed", "errors": {"details": str(e)}}, 400
        except Exception as e:
            return {"success": False, "message": "Something went wrong", "errors": str(e)}, 400

        caption_text = regenerated.get("content", "")
        hashtags = regenerated.get("hashtags", "")
        if hashtags:
            caption_text = f"{caption_text}\n\n{hashtags}"

    # Regenerate image and/or video if requested (both share the Gemini key)
    image_path = ""
    image_url = ""
    image_prompt = ""
    video_path = ""
    video_url = ""
    video_prompt = ""
    if update_image or update_video:
        api_key, record = await _load_gemini_key(db, user)
        if not api_key:
            return {
                "success": False,
                "message": "No Gemini API key configured. Save one via POST /api/ai-keys/gemini/",
                "errors": {},
            }, 400

        image_platform = _normalize_platform(request.platform)

        if update_image:
            image_model = request.model or (record.default_image_model if record else "") or settings.GEMINI_IMAGE_MODEL
            try:
                gen = generate_content_image(
                    api_key=api_key,
                    text=request.description,
                    platform=image_platform,
                    brand_summary=request.brand_summary,
                    model=image_model,
                    prompt_override=request.prompt,
                )
                image_path = gen["path"]
                image_prompt = gen["prompt"]
                image_url = f"{settings.BASE_URL}{settings.MEDIA_URL_PREFIX}/{image_path}"
                # Record the generated image as an AI asset (best-effort).
                await _record_ai_asset(db, user.id, image_path, prompt=image_prompt, model=image_model)
            except (GeminiError, Exception) as e:
                return {"success": False, "message": "Image generation failed", "errors": {"details": str(e)}}, 400

        if update_video:
            video_model = (record.default_video_model if record else "") or settings.GEMINI_VIDEO_MODEL
            try:
                vgen = generate_content_video(
                    api_key=api_key,
                    text=request.description,
                    platform=image_platform,
                    brand_summary=request.brand_summary,
                    model=video_model,
                    prompt_override=request.prompt,
                )
                video_path = vgen["path"]
                video_prompt = vgen["prompt"]
                video_url = f"{settings.BASE_URL}{settings.MEDIA_URL_PREFIX}/{video_path}"
            except (VideoGenerationError, Exception) as e:
                return {"success": False, "message": "Video generation failed", "errors": {"details": str(e)}}, 400

    # Apply updates to every post in the day group
    # Primary media on the Post row: video takes precedence over image
    # (both are also attached as PostMedia rows).
    primary_media = video_path or image_path or None
    updated_posts = []
    post_ids = []
    for post in posts:
        if update_caption:
            post.caption = caption_text
            post.caption_regen_count += 1
        if primary_media:
            post.media = primary_media
        if update_image and image_path:
            post.image_regen_count += 1
        if update_video and video_path:
            post.video_regen_count += 1
        if image_path:
            db.add(PostMedia(post_id=post.id, file=image_path))
        if video_path:
            db.add(PostMedia(post_id=post.id, file=video_path))
        await db.flush()
        post_ids.append(post.id)

        media_list = []
        if post.media:
            media_list.append(f"{settings.BASE_URL}{settings.MEDIA_URL_PREFIX}/{post.media}")
        updated_posts.append({
            "post_id": post.id,
            "user_id": post.user_id,
            "day": request.day,
            "day_group_id": post.day_group_id,
            "platform": post.platform,
            "caption": post.caption,
            "image_url": image_url if image_path else (media_list[0] if media_list and not video_url else ""),
            "video_url": video_url,
            "scheduled_time": post.scheduled_time.isoformat() if post.scheduled_time else None,
            "status": post.status,
            "regen_counts": {
                "caption": post.caption_regen_count,
                "image": post.image_regen_count,
                "video": post.video_regen_count,
            },
        })

    # ── Credit logging (one log per action, once per day group) ───────
    if update_caption:
        await log_credit_async(
            db, user.id, ACTION_CAPTION_GENERATION,
            reference_type="post",
            reference_id=post_ids[0] if post_ids else None,
            meta={"day_group_id": request.day_group_id, "day": request.day},
            note="regenerate-day-group caption",
        )
    if update_image and image_path:
        await log_credit_async(
            db, user.id, ACTION_IMAGE_GENERATION,
            reference_type="post",
            reference_id=post_ids[0] if post_ids else None,
            meta={"day_group_id": request.day_group_id, "day": request.day, "model": image_model, "media": image_path},
            note="regenerate-day-group image",
        )
    if update_video and video_path:
        await log_credit_async(
            db, user.id, ACTION_VIDEO_GENERATION,
            reference_type="post",
            reference_id=post_ids[0] if post_ids else None,
            meta={"day_group_id": request.day_group_id, "day": request.day, "model": video_model, "media": video_path},
            note="regenerate-day-group video",
        )

    # Build the single AI caption item for the response (same shape as generate-captions)
    scheduled_time_iso = updated_posts[0]["scheduled_time"] if updated_posts else request.scheduled_at
    items = []
    if update_caption:
        items.append({
            "day": request.day,
            "scheduled_at": scheduled_time_iso,
            "content": regenerated.get("content", ""),
            "hashtags": hashtags,
            "day_group_id": request.day_group_id,
            "post_ids": post_ids,
            "image_url": image_url,
            "video_url": video_url,
        })

    day_groups = [{
        "day": request.day,
        "day_group_id": request.day_group_id,
        "scheduled_time": scheduled_time_iso,
        "post_ids": post_ids,
    }]

    return {
        "success": True,
        "message": f"Day group regenerated ({len(updated_posts)} post(s) updated)",
        "data": {
            "items": items,
            "posts": updated_posts,
            "day_groups": day_groups,
            "total_posts": len(updated_posts),
            "total_days": 1,
        },
    }


# ──────────────────────────────────────────────────────────────────────────
# Stage 5 — Final submit (finalize edits + schedule pending posts)
# ──────────────────────────────────────────────────────────────────────────

@router.post("/final-submit/")
async def final_submit_endpoint(
    request: FinalSubmitRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Stage 5 — Submit button.

    For each item (identified by `day_group_id`):
      1. Find all posts owned by the current user in that group.
      2. Apply the final edited `caption` / `media` (None = leave as-is).
      3. Flip status pending → scheduled so the auto scheduler publishes them.

    NOTE: Credit logging is NOT done here — it happens at generation time
    (generate-captions / regenerate-image / regenerate-day-group etc.),
    because that's where the actual AI resource is consumed. This endpoint
    only finalizes user edits and schedules.
    """
    if not request.items:
        return {"success": False, "message": "items is required", "errors": {}}, 400

    scheduled_post_ids: list[int] = []
    skipped_groups: list[str] = []

    for item in request.items:
        if not item.day_group_id or not item.day_group_id.strip():
            skipped_groups.append(item.day_group_id or "")
            continue

        result = await db.execute(
            select(Post).where(
                Post.day_group_id == item.day_group_id,
                Post.user_id == user.id,
            )
        )
        posts = result.scalars().all()
        if not posts:
            skipped_groups.append(item.day_group_id)
            continue

        for post in posts:
            if item.caption is not None:
                post.caption = item.caption
            if item.media is not None:
                post.media = item.media
            # Only flip posts that are still pending → scheduled.
            # (Already-scheduled/posted posts are left untouched.)
            if post.status == Post.STATUS_PENDING:
                post.status = Post.STATUS_SCHEDULED
            scheduled_post_ids.append(post.id)

    await db.flush()

    return {
        "success": True,
        "message": f"{len(scheduled_post_ids)} post(s) scheduled",
        "data": {
            "scheduled_count": len(scheduled_post_ids),
            "post_ids": scheduled_post_ids,
            "skipped_groups": skipped_groups,
        },
    }