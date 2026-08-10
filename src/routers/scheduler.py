"""Scheduler router — run scheduler + send-task to agent."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.config import settings
from src.core.database import get_db
from src.core.websocket_manager import registry
from src.dependencies.auth import get_current_user
from src.models.accounts import User
from src.models.posts import Post
from src.models.post_media import PostMedia

router = APIRouter(prefix="/scheduler", tags=["scheduler"])


async def _send_post_to_agent(post: Post, user_id: int) -> bool:
    media_urls = []
    for m in post.media_files:
        media_urls.append(f"{settings.BASE_URL}{settings.MEDIA_URL_PREFIX}/{m.file}")
    if not media_urls and post.media:
        media_urls.append(f"{settings.BASE_URL}{settings.MEDIA_URL_PREFIX}/{post.media}")

    return await registry.send_to_user(user_id, {
        "type": "send_task",
        "post_id": post.id,
        "platform": post.platform,
        "caption": post.caption,
        "media": media_urls,
    })


@router.get("/run/")
async def run_scheduler(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(Post).options(selectinload(Post.media_files))
        .where(Post.status == Post.STATUS_SCHEDULED, Post.scheduled_time <= now)
    )
    scheduled_posts = result.scalars().all()

    processed_ids = []
    skipped_ids = []
    for post in scheduled_posts:
        sent = await _send_post_to_agent(post, post.user_id)
        if sent:
            post.status = Post.STATUS_PROCESSING
            processed_ids.append(post.id)
        else:
            # Agent offline — leave as SCHEDULED so it retries on next run
            skipped_ids.append(post.id)

    await db.flush()
    return {
        "success": True,
        "message": "scheduler sent tasks to local agent successfully",
        "processed_post_ids": processed_ids,
        "skipped_post_ids": skipped_ids,
    }


@router.post("/send-task/{post_id}/")
async def send_task_to_agent(post_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Post).options(selectinload(Post.media_files))
        .where(Post.id == post_id, Post.user_id == user.id)
    )
    post = result.scalar_one_or_none()
    if not post:
        return {"success": False, "message": "Post not found"}, 404

    sent = await _send_post_to_agent(post, user.id)
    if sent:
        post.status = Post.STATUS_PROCESSING
    await db.flush()

    return {
        "success": sent,
        "message": "Task sent to local agent" if sent else "No agent online — post remains scheduled",
        "post_id": post.id,
        "user_id": post.user_id,
        "platform": post.platform,
    }