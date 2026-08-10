"""Content plans router — full CRUD + item-level operations."""
import os
import shutil
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.database import get_db
from src.dependencies.auth import get_current_user
from src.models.accounts import User
from src.models.posts import Post
from src.models.post_media import PostMedia
from src.models.content_plans import ContentPlan, ContentPlanItem, UserAIKey
from sqlalchemy.orm import selectinload, joinedload
from src.schemas.content_plans import (
    ContentPlanCreate, ContentPlanSchedule, ContentPlanItemUpdate,
    RegenerateCaptionRequest, RegenerateMediaRequest,
)
from src.services.crypto import encrypt, decrypt
from src.services.images import validate_api_key
from src.services import schedule as schedule_svc

router = APIRouter(prefix="/api", tags=["content_plans"])

VALID_IMAGE_MODELS = {
    "gemini-2.5-flash-image",
    "imagen-3.0-generate-002", "imagen-4.0-generate-001",
}
VALID_VIDEO_MODELS = {
    "veo-3.1-generate-preview",
}
VALID_MEDIA_TYPES = {"image", "video"}

GEMINI_IMAGE_MODEL_CHOICES = [
    {"code": c, "label": l, "is_default": c == settings.GEMINI_IMAGE_MODEL}
    for c, l in [
        ("gemini-2.5-flash-image", "Gemini 2.5 Flash Image"),
        ("imagen-3.0-generate-002", "Imagen 3"),
        ("imagen-4.0-generate-001", "Imagen 4"),
    ]
]
GEMINI_VIDEO_MODEL_CHOICES = [
    {"code": c, "label": l, "is_default": c == settings.GEMINI_VIDEO_MODEL}
    for c, l in [
        ("veo-3.1-generate-preview", "Veo 3.1"),
    ]
]


def _ok(data=None, message="OK", http=200):
    payload = {"success": True, "message": message}
    if data is not None:
        payload["data"] = data
    return payload


def _err(message, errors=None, http=400):
    return {"success": False, "message": message, "errors": errors or {}}, http


def _item_to_dict(item) -> dict:
    media_url = None
    if (item.media_type or "image") == "video" and item.video:
        media_url = f"{settings.BASE_URL}{settings.MEDIA_URL_PREFIX}/{item.video}"
    elif item.image:
        media_url = f"{settings.BASE_URL}{settings.MEDIA_URL_PREFIX}/{item.image}"

    return {
        "id": item.id,
        "sequence": item.sequence,
        "platform": item.platform,
        "topic": item.topic,
        "caption": item.caption,
        "hashtags": item.hashtags,
        "image": f"{settings.BASE_URL}{settings.MEDIA_URL_PREFIX}/{item.image}" if item.image else None,
        "image_prompt": item.image_prompt,
        "video": f"{settings.BASE_URL}{settings.MEDIA_URL_PREFIX}/{item.video}" if item.video else None,
        "video_prompt": item.video_prompt,
        "media_type": item.media_type,
        "media_url": media_url,
        "scheduled_time": item.scheduled_time.isoformat() if item.scheduled_time else None,
        "status": item.status,
        "caption_regen_count": item.caption_regen_count,
        "image_regen_count": item.image_regen_count,
        "video_regen_count": item.video_regen_count,
        "error_message": item.error_message,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
    }


def _plan_to_dict(plan, include_items: bool = False) -> dict:
    d = {
        "id": plan.id,
        "website_url": plan.website_url,
        "duration_days": plan.duration_days,
        "frequency": plan.frequency,
        "custom_interval_days": plan.custom_interval_days,
        "platforms": plan.platforms,
        "start_date": plan.start_date.isoformat() if plan.start_date else None,
        "posting_time": plan.posting_time.isoformat() if plan.posting_time else None,
        "total_posts": plan.total_posts,
        "media_type": plan.media_type,
        "image_model": plan.image_model,
        "video_model": plan.video_model,
        "status": plan.status,
        "progress": plan.progress,
        "error_message": plan.error_message,
        "created_at": plan.created_at.isoformat() if plan.created_at else None,
        "updated_at": plan.updated_at.isoformat() if plan.updated_at else None,
    }
    if include_items:
        d["brand_summary"] = plan.brand_summary
        d["brand_keywords"] = plan.brand_keywords
        d["items"] = [_item_to_dict(i) for i in plan.items]
    return d


# ── Gemini key management ────────────────────────────────────────────

@router.get("/ai-keys/gemini/")
async def get_gemini_key(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(UserAIKey).where(UserAIKey.user_id == user.id))
    record = result.scalar_one_or_none()
    if not record:
        return _ok({"configured": False, "last4": "", "validated_at": None,
                     "default_image_model": "", "default_video_model": ""})
    return _ok({
        "configured": bool(record.gemini_key_encrypted),
        "last4": record.gemini_key_last4,
        "validated_at": record.gemini_validated_at.isoformat() if record.gemini_validated_at else None,
        "default_image_model": record.default_image_model,
        "default_video_model": record.default_video_model,
    })


@router.post("/ai-keys/gemini/")
async def save_gemini_key(data: dict, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    api_key = (data.get("api_key") or "").strip()
    if not api_key:
        return _err("api_key is required")
    try:
        valid = validate_api_key(api_key)
    except Exception:
        valid = False

    result = await db.execute(select(UserAIKey).where(UserAIKey.user_id == user.id))
    record = result.scalar_one_or_none()
    if not record:
        record = UserAIKey(user_id=user.id)
        db.add(record)
    record.gemini_key_encrypted = encrypt(api_key)
    record.gemini_key_last4 = api_key[-4:]
    record.gemini_validated_at = datetime.now(timezone.utc) if valid else None
    await db.flush()
    return _ok({"configured": True, "last4": record.gemini_key_last4,
                "validated": bool(valid), "validated_at": record.gemini_validated_at.isoformat() if record.gemini_validated_at else None},
               message="Gemini key saved")


@router.patch("/ai-keys/gemini/")
async def update_gemini_defaults(data: dict, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(UserAIKey).where(UserAIKey.user_id == user.id))
    record = result.scalar_one_or_none()
    if not record:
        record = UserAIKey(user_id=user.id)
        db.add(record)
    if "default_image_model" in data:
        record.default_image_model = data["default_image_model"] or ""
    if "default_video_model" in data:
        record.default_video_model = data["default_video_model"] or ""
    await db.flush()
    return _ok({"configured": bool(record.gemini_key_encrypted),
                "last4": record.gemini_key_last4,
                "default_image_model": record.default_image_model,
                "default_video_model": record.default_video_model},
               message="Defaults updated")


@router.delete("/ai-keys/gemini/")
async def delete_gemini_key(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(UserAIKey).where(UserAIKey.user_id == user.id))
    record = result.scalar_one_or_none()
    if record:
        await db.delete(record)
    return _ok(message="Gemini key removed")


@router.get("/ai-keys/gemini/models/")
async def get_gemini_models(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    # Check if the user has a saved default model override
    key_result = await db.execute(select(UserAIKey).where(UserAIKey.user_id == user.id))
    record = key_result.scalar_one_or_none()

    user_image_default = (record.default_image_model if record and record.default_image_model else None) or settings.GEMINI_IMAGE_MODEL
    user_video_default = (record.default_video_model if record and record.default_video_model else None) or settings.GEMINI_VIDEO_MODEL

    # Mark is_default based on the user's saved preference (or the global default)
    image_models = [
        {**m, "is_default": m["code"] == user_image_default}
        for m in GEMINI_IMAGE_MODEL_CHOICES
    ]
    video_models = [
        {**m, "is_default": m["code"] == user_video_default}
        for m in GEMINI_VIDEO_MODEL_CHOICES
    ]

    return _ok({
        "image_models": image_models,
        "video_models": video_models,
        "default_image_model": user_image_default,
        "default_video_model": user_video_default,
    })


# ── Plans CRUD ───────────────────────────────────────────────────────

@router.get("/content-plans/")
async def list_plans(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ContentPlan).where(ContentPlan.user_id == user.id).order_by(ContentPlan.created_at.desc()))
    plans = result.scalars().all()
    return _ok([_plan_to_dict(p) for p in plans])


@router.post("/content-plans/")
async def create_plan(data: ContentPlanCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    key_result = await db.execute(select(UserAIKey).where(UserAIKey.user_id == user.id))
    record = key_result.scalar_one_or_none()
    if not record or not record.gemini_key_encrypted:
        return _err("Add your Gemini API key before creating a content plan.",
                    errors={"gemini_api_key": "missing"}, http=400)

    # Check no plan currently generating
    gen_result = await db.execute(
        select(ContentPlan).where(ContentPlan.user_id == user.id, ContentPlan.status == "generating")
    )
    if gen_result.scalar_one_or_none():
        return _err("Another plan is currently generating. Please wait for it to finish.", http=409)

    image_model = data.image_model or record.default_image_model or ""
    video_model = data.video_model or record.default_video_model or ""

    plan = ContentPlan(
        user_id=user.id,
        website_url=str(data.website_url),
        duration_days=data.duration_days,
        platforms=data.platforms,
        frequency=data.frequency or "daily",
        custom_interval_days=data.custom_interval_days or 1,
        start_date=data.start_date,
        posting_time=data.posting_time,
        media_type=data.media_type or "image",
        image_model=image_model,
        video_model=video_model,
        status="generating",
    )
    db.add(plan)
    await db.flush()

    # Pre-compute total_posts
    slots = schedule_svc.slots_per_platform(plan)
    plan.total_posts = slots * max(1, len(plan.platforms))
    await db.flush()

    # Kick off async generation via Celery
    try:
        from src.celery_tasks.content_plans import generate_content_plan
        generate_content_plan.delay(plan.id)
    except Exception:
        pass  # Eager fallback handled in task module

    return _ok({"plan_id": plan.id, "total_posts": plan.total_posts, "status": plan.status},
               message="Plan created and generation started", http=201)


@router.get("/content-plans/{plan_id}/")
async def get_plan(plan_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ContentPlan)
        .options(selectinload(ContentPlan.items))
        .where(ContentPlan.id == plan_id, ContentPlan.user_id == user.id)
    )
    plan = result.scalar_one_or_none()
    if not plan:
        return _err("Plan not found", http=404)
    return _ok(_plan_to_dict(plan, include_items=True))


@router.delete("/content-plans/{plan_id}/")
async def delete_plan(plan_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ContentPlan).options(selectinload(ContentPlan.items))
        .where(ContentPlan.id == plan_id, ContentPlan.user_id == user.id)
    )
    plan = result.scalar_one_or_none()
    if not plan:
        return _err("Plan not found", http=404)
    if plan.status not in {"draft", "pending_review", "failed", "approved"}:
        return _err(f"Cannot delete a plan in status '{plan.status}'.", http=409)
    await db.delete(plan)
    return _ok(message="Plan deleted")


@router.get("/content-plans/{plan_id}/progress/")
async def get_plan_progress(plan_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ContentPlan).where(ContentPlan.id == plan_id, ContentPlan.user_id == user.id))
    plan = result.scalar_one_or_none()
    if not plan:
        return _err("Plan not found", http=404)
    # Count completed items
    items_result = await db.execute(
        select(ContentPlanItem).where(ContentPlanItem.plan_id == plan.id)
    )
    items = items_result.scalars().all()
    completed = sum(1 for i in items if i.status not in ["pending_review", "failed"])
    return _ok({
        "plan_id": plan.id, "status": plan.status, "progress": plan.progress,
        "completed_items": completed, "total_posts": plan.total_posts,
        "error_message": plan.error_message,
    })


@router.post("/content-plans/{plan_id}/schedule/")
async def schedule_plan(plan_id: int, data: ContentPlanSchedule, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ContentPlan).options(selectinload(ContentPlan.items))
        .where(ContentPlan.id == plan_id, ContentPlan.user_id == user.id)
    )
    plan = result.scalar_one_or_none()
    if not plan:
        return _err("Plan not found", http=404)
    if plan.status not in {"pending_review", "approved"}:
        return _err(f"Cannot schedule a plan in status '{plan.status}'.", http=409)

    from datetime import date as date_cls
    if data.start_date < date_cls.today():
        return _err("start_date cannot be in the past")

    plan.frequency = data.frequency
    plan.custom_interval_days = data.custom_interval_days or 1
    plan.start_date = data.start_date
    plan.posting_time = data.posting_time
    await db.flush()

    # Re-spread items
    slot_times = schedule_svc.build(plan)
    if slot_times:
        items_result = await db.execute(
            select(ContentPlanItem).where(ContentPlanItem.plan_id == plan.id)
            .order_by(ContentPlanItem.sequence, ContentPlanItem.id)
        )
        items_by_seq: dict[int, list] = {}
        for item in items_result.scalars().all():
            items_by_seq.setdefault(item.sequence, []).append(item)
        for seq, item_list in items_by_seq.items():
            idx = seq - 1
            if 0 <= idx < len(slot_times):
                for it in item_list:
                    it.scheduled_time = slot_times[idx]
    await db.flush()
    return _ok(_plan_to_dict(plan, include_items=True), message="Schedule saved")


@router.post("/content-plans/{plan_id}/approve/")
async def approve_plan(plan_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ContentPlan).options(selectinload(ContentPlan.items))
        .where(ContentPlan.id == plan_id, ContentPlan.user_id == user.id)
    )
    plan = result.scalar_one_or_none()
    if not plan:
        return _err("Plan not found", http=404)

    if plan.status == "scheduled":
        items_result = await db.execute(
            select(ContentPlanItem).where(ContentPlanItem.plan_id == plan.id, ContentPlanItem.post_id.is_not(None))
        )
        post_ids = [i.post_id for i in items_result.scalars().all()]
        return _ok({"scheduled_count": len(post_ids), "post_ids": post_ids}, message="Plan already scheduled")

    if not plan.start_date or not plan.posting_time:
        return _err("Set start_date and posting_time via /schedule/ before approving.", http=400)

    items_result = await db.execute(
        select(ContentPlanItem).where(
            ContentPlanItem.plan_id == plan.id, ContentPlanItem.status == "approved"
        ).with_for_update()
    )
    eligible = items_result.scalars().all()
    if not eligible:
        return _err("No approved items to schedule.", http=400)

    # Check media
    missing_media = []
    for it in eligible:
        if (it.media_type or "image") == "video":
            if not it.video:
                missing_media.append(it.id)
        else:
            if not it.image:
                missing_media.append(it.id)
    if missing_media:
        return _err("Some approved items have no media yet.",
                    errors={"items_without_media": missing_media}, http=400)

    now = datetime.now(timezone.utc)
    post_ids = []
    for item in eligible:
        if not item.scheduled_time or item.scheduled_time < now:
            continue
        caption_text = item.caption.strip()
        if item.hashtags.strip():
            caption_text = f"{caption_text}\n\n{item.hashtags.strip()}"
        media_field = item.video if (item.media_type or "image") == "video" else item.image

        post = Post(
            user_id=plan.user_id,
            caption=caption_text,
            platform=item.platform,
            scheduled_time=item.scheduled_time,
            status=Post.STATUS_SCHEDULED,
            media=media_field,
        )
        db.add(post)
        await db.flush()
        if media_field:
            db.add(PostMedia(post_id=post.id, file=media_field))

        item.post_id = post.id
        item.status = "scheduled"
        post_ids.append(post.id)

    plan.status = "scheduled"
    await db.flush()
    return _ok({"scheduled_count": len(post_ids), "post_ids": post_ids}, message="Plan scheduled")


# ── Item-level operations ────────────────────────────────────────────

async def _get_item(item_id: int, user_id: int, db: AsyncSession) -> ContentPlanItem | None:
    result = await db.execute(
        select(ContentPlanItem)
        .options(joinedload(ContentPlanItem.plan))
        .join(ContentPlan).where(
            ContentPlanItem.id == item_id, ContentPlan.user_id == user_id
        )
    )
    return result.scalar_one_or_none()


@router.patch("/content-plans/items/{item_id}/")
async def update_item(item_id: int, data: ContentPlanItemUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    item = await _get_item(item_id, user.id, db)
    if not item:
        return _err("Item not found", http=404)
    if item.plan.status not in {"pending_review", "approved"}:
        return _err(f"Plan status '{item.plan.status}' does not allow edits.", http=409)

    if data.caption is not None:
        item.caption = data.caption
    if data.hashtags is not None:
        item.hashtags = data.hashtags
    if data.scheduled_time is not None:
        item.scheduled_time = data.scheduled_time
    if data.media_type is not None:
        if data.media_type not in VALID_MEDIA_TYPES:
            return _err(f"media_type must be one of {sorted(VALID_MEDIA_TYPES)}")
        if item.status in {"approved", "scheduled", "rejected"}:
            return _err(f"Cannot change media_type when item is '{item.status}'.", http=409)
        item.media_type = data.media_type
    await db.flush()
    return _ok(_item_to_dict(item))


@router.post("/content-plans/items/{item_id}/regenerate-caption/")
async def regen_caption(item_id: int, data: RegenerateCaptionRequest, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    item = await _get_item(item_id, user.id, db)
    if not item:
        return _err("Item not found", http=404)
    if item.caption_regen_count >= settings.CONTENT_PLAN_MAX_REGENS:
        return _err(f"Caption regeneration limit reached ({settings.CONTENT_PLAN_MAX_REGENS}).", http=429)
    if data.topic:
        item.topic = data.topic
        await db.flush()
    try:
        from src.celery_tasks.content_plans import regenerate_caption
        regenerate_caption.delay(item.id)
    except Exception:
        pass
    return _ok(_item_to_dict(item), message="Caption regeneration queued")


@router.post("/content-plans/items/{item_id}/approve-caption/")
async def approve_caption(item_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    item = await _get_item(item_id, user.id, db)
    if not item:
        return _err("Item not found", http=404)
    if not (item.caption or "").strip():
        return _err("Cannot approve an empty caption", http=400)

    is_video = (item.media_type or "image") == "video"
    item.status = "video_generating" if is_video else "image_generating"
    await db.flush()

    try:
        from src.celery_tasks.content_plans import dispatch_media_generation
        dispatch_media_generation(item.id, "")
    except Exception:
        pass
    return _ok(_item_to_dict(item),
               message="Caption approved, video generation started" if is_video else "Caption approved, image generation started")


@router.post("/content-plans/items/{item_id}/regenerate-image/")
async def regen_image(item_id: int, data: RegenerateMediaRequest, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    item = await _get_item(item_id, user.id, db)
    if not item:
        return _err("Item not found", http=404)
    if item.image_regen_count >= settings.CONTENT_PLAN_MAX_REGENS:
        return _err(f"Image regeneration limit reached ({settings.CONTENT_PLAN_MAX_REGENS}).", http=429)
    try:
        from src.celery_tasks.content_plans import generate_image_for_item
        generate_image_for_item.delay(item.id, data.prompt_override)
    except Exception:
        pass
    return _ok(_item_to_dict(item), message="Image regeneration queued")


@router.post("/content-plans/items/{item_id}/regenerate-video/")
async def regen_video(item_id: int, data: RegenerateMediaRequest, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    item = await _get_item(item_id, user.id, db)
    if not item:
        return _err("Item not found", http=404)
    if item.video_regen_count >= settings.CONTENT_PLAN_MAX_REGENS:
        return _err(f"Video regeneration limit reached ({settings.CONTENT_PLAN_MAX_REGENS}).", http=429)
    try:
        from src.celery_tasks.content_plans import generate_video_for_item
        generate_video_for_item.delay(item.id, data.prompt_override)
    except Exception:
        pass
    return _ok(_item_to_dict(item), message="Video regeneration queued")


@router.post("/content-plans/items/{item_id}/upload-image/")
async def upload_image(item_id: int, image: UploadFile = File(...), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    item = await _get_item(item_id, user.id, db)
    if not item:
        return _err("Item not found", http=404)

    contents = await image.read()
    is_video = (item.media_type or "image") == "video"
    ext = ".mp4" if is_video else ".png"
    filename = f"content_plans/{item.plan_id}/{item.id}-{int(datetime.now().timestamp())}{ext}"
    full_path = settings.MEDIA_DIR / filename
    full_path.parent.mkdir(parents=True, exist_ok=True)
    full_path.write_bytes(contents)

    if is_video:
        item.video = filename
        item.status = "video_pending_review"
    else:
        item.image = filename
        item.status = "image_pending_review"
    await db.flush()
    return _ok(_item_to_dict(item), message="Media uploaded")


@router.post("/content-plans/items/{item_id}/upload-media/")
async def upload_media(item_id: int, image: UploadFile = File(...), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await upload_image(item_id, image, user, db)


@router.post("/content-plans/items/{item_id}/approve-image/")
async def approve_image(item_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    item = await _get_item(item_id, user.id, db)
    if not item:
        return _err("Item not found", http=404)
    is_video = (item.media_type or "image") == "video"
    media_file = item.video if is_video else item.image
    if not media_file:
        return _err(f"Item has no {'video' if is_video else 'image'} to approve", http=400)
    item.status = "approved"
    await db.flush()
    return _ok(_item_to_dict(item), message="Item approved")


@router.post("/content-plans/items/{item_id}/approve-media/")
async def approve_media(item_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await approve_image(item_id, user, db)


@router.post("/content-plans/items/{item_id}/reject/")
async def reject_item(item_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    item = await _get_item(item_id, user.id, db)
    if not item:
        return _err("Item not found", http=404)
    item.status = "rejected"
    await db.flush()
    return _ok(_item_to_dict(item), message="Item rejected")