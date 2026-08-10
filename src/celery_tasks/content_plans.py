"""
Celery tasks for content plans — replaces apps/content_plans/tasks.py.

Runs the heavy bulk caption + image generation in the background.
"""
from celery import shared_task
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from src.core.config import settings
from src.models.content_plans import ContentPlan, ContentPlanItem
from src.services import scraper as scraper_svc
from src.services import brand_summary as brand_svc
from src.services import captions as captions_svc
from src.services import schedule as schedule_svc
from src.services import images as images_svc
from src.services import videos as videos_svc
from src.services.zettalgor import ZettalgorError
from src.services.credits import log_credit_sync
from src.models.credits import (
    ACTION_IMAGE_GENERATION, ACTION_VIDEO_GENERATION,
    ACTION_CAPTION_GENERATION, ACTION_CONTENT_PLAN_GENERATION,
)


_sync_engine = None


def _get_sync_session() -> Session:
    global _sync_engine
    if _sync_engine is None:
        _sync_engine = create_engine(settings.DATABASE_SYNC_URL, pool_pre_ping=True)
    return Session(_sync_engine)


def _set_plan_status(session, plan, status, **fields):
    plan.status = status
    for k, v in fields.items():
        setattr(plan, k, v)
    session.commit()


@shared_task(name="src.celery_tasks.content_plans.generate_content_plan")
def generate_content_plan(plan_id: int):
    session = _get_sync_session()
    try:
        plan = session.query(ContentPlan).get(plan_id)
        if not plan:
            return f"Plan {plan_id} missing"

        _set_plan_status(session, plan, "generating", progress=0, error_message="")

        try:
            snapshot = scraper_svc.fetch(plan.website_url)
        except Exception as exc:
            _set_plan_status(session, plan, "failed", error_message=f"Scrape failed: {exc}")
            raise

        slot_count = schedule_svc.slots_per_platform(plan)

        try:
            brand = brand_svc.summarise(snapshot, slot_count)
        except Exception as exc:
            _set_plan_status(session, plan, "failed", error_message=f"Brand summary failed: {exc}")
            raise

        plan.brand_summary = brand.get("summary", "")
        plan.brand_keywords = brand.get("keywords", [])
        session.commit()

        topics = brand.get("topics", [])
        slot_times = schedule_svc.build(plan)

        items = []
        for slot_idx in range(slot_count):
            topic = topics[slot_idx] if slot_idx < len(topics) else f"Post {slot_idx+1}"
            scheduled_at = slot_times[slot_idx] if slot_idx < len(slot_times) else None
            for platform in plan.platforms:
                item = ContentPlanItem(
                    plan_id=plan.id,
                    sequence=slot_idx + 1,
                    platform=platform,
                    topic=topic,
                    scheduled_time=scheduled_at,
                    status="pending_review",
                    media_type=plan.media_type or "image",
                )
                session.add(item)
                items.append(item)
        session.commit()

        plan.total_posts = len(items)
        session.commit()

        # Generate captions
        total = len(items) or 1
        done = 0
        for item in items:
            try:
                cap = captions_svc.generate(item.topic, item.platform, plan.brand_summary)
                item.caption = cap.get("caption", "")
                item.hashtags = cap.get("hashtags", "")
                item.status = "pending_review"
            except ZettalgorError as exc:
                item.status = "failed"
                item.error_message = str(exc)
            except Exception as exc:
                item.status = "failed"
                item.error_message = f"Caption generation error: {exc}"
            session.commit()
            done += 1
            plan.progress = int(done * 100 / total)
            session.commit()

        plan.status = "pending_review"
        plan.progress = 100
        session.commit()

        # Credit log — one charge for the whole content-plan generation.
        # (Silent skip if no rate configured.)
        log_credit_sync(
            session, plan.user_id, ACTION_CONTENT_PLAN_GENERATION,
            reference_type="content_plan",
            reference_id=plan.id,
            meta={"items": len(items), "platforms": plan.platforms},
            note="content plan generation",
        )
        session.commit()
        return f"Plan {plan_id} generated {len(items)} items"
    finally:
        session.close()


@shared_task(name="src.celery_tasks.content_plans.regenerate_caption")
def regenerate_caption(item_id: int):
    session = _get_sync_session()
    try:
        item = session.query(ContentPlanItem).get(item_id)
        if not item:
            return f"Item {item_id} missing"
        plan = item.plan
        # Reset status + error before regenerating (matches Django behavior)
        item.status = "pending_review"
        item.error_message = ""
        session.commit()
        try:
            cap = captions_svc.generate(item.topic, item.platform, plan.brand_summary)
            item.caption = cap.get("caption", "")
            item.hashtags = cap.get("hashtags", "")
            item.status = "pending_review"
            item.caption_regen_count += 1
        except Exception as exc:
            item.status = "failed"
            item.error_message = str(exc)
        session.commit()
        # Credit log — one charge for the caption regeneration.
        if item.caption:
            log_credit_sync(
                session, plan.user_id, ACTION_CAPTION_GENERATION,
                reference_type="content_plan_item",
                reference_id=item.id,
                meta={"plan_id": plan.id},
                note="content plan caption regen",
            )
            session.commit()
        return f"Caption regenerated for item {item_id}"
    finally:
        session.close()


@shared_task(name="src.celery_tasks.content_plans.generate_image_for_item")
def generate_image_for_item(item_id: int, prompt_override: str = ""):
    session = _get_sync_session()
    try:
        item = session.query(ContentPlanItem).get(item_id)
        if not item:
            return f"Item {item_id} missing"
        # Set pre-generation status (matches Django behavior)
        item.status = "image_generating"
        item.error_message = ""
        session.commit()
        try:
            path = images_svc.generate(item, item.plan.brand_summary, prompt_override)
            item.image = path
            item.status = "image_pending_review"
            # Only increment regen count when prompt_override provided (Django behavior)
            if prompt_override:
                item.image_regen_count += 1
        except Exception as exc:
            item.status = "failed"
            item.error_message = str(exc)
        session.commit()
        # Credit log — one charge for the image generation.
        if item.image:
            log_credit_sync(
                session, item.plan.user_id, ACTION_IMAGE_GENERATION,
                reference_type="content_plan_item",
                reference_id=item.id,
                meta={"plan_id": item.plan_id, "media": item.image},
                note="content plan image",
            )
            session.commit()
        return f"Image generated for item {item_id}"
    finally:
        session.close()


@shared_task(name="src.celery_tasks.content_plans.generate_video_for_item")
def generate_video_for_item(item_id: int, prompt_override: str = ""):
    session = _get_sync_session()
    try:
        item = session.query(ContentPlanItem).get(item_id)
        if not item:
            return f"Item {item_id} missing"
        # Set pre-generation status (matches Django behavior)
        item.status = "video_generating"
        item.error_message = ""
        session.commit()
        try:
            path = videos_svc.generate(item, item.plan.brand_summary, prompt_override)
            item.video = path
            item.status = "video_pending_review"
            # Only increment regen count when prompt_override provided (Django behavior)
            if prompt_override:
                item.video_regen_count += 1
        except Exception as exc:
            item.status = "failed"
            item.error_message = str(exc)
        session.commit()
        # Credit log — one charge for the video generation.
        if item.video:
            log_credit_sync(
                session, item.plan.user_id, ACTION_VIDEO_GENERATION,
                reference_type="content_plan_item",
                reference_id=item.id,
                meta={"plan_id": item.plan_id, "media": item.video},
                note="content plan video",
            )
            session.commit()
        return f"Video generated for item {item_id}"
    finally:
        session.close()


def dispatch_media_generation(item_id: int, prompt_override: str = ""):
    """Dispatch image or video generation based on item media_type."""
    session = _get_sync_session()
    try:
        item = session.query(ContentPlanItem).get(item_id)
        if not item:
            return
        if (item.media_type or "image") == "video":
            generate_video_for_item.delay(item_id, prompt_override)
        else:
            generate_image_for_item.delay(item_id, prompt_override)
    finally:
        session.close()