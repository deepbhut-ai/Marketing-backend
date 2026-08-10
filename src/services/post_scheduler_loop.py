"""
Automatic in-process post scheduler.

Runs as a background asyncio task inside the FastAPI process. Every few
seconds it looks for posts whose scheduled_time has arrived and hands
them to the connected agent over WebSocket. Because it lives in the same
process as the WebSocket registry, it can actually reach the agent
(unlike the Celery beat path, which runs in a separate process with an
empty in-memory registry).

Status transitions performed here:
    SCHEDULED -> PROCESSING   (agent received the task)
    SCHEDULED -> SCHEDULED     (agent offline; left for retry next tick)
"""
import asyncio
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.core.config import settings
from src.core.database import AsyncSessionLocal
from src.core.websocket_manager import registry
from src.models.posts import Post
from src.services.agent_starter import ensure_agent_running

# How often to scan for due posts (seconds).
POLL_INTERVAL_SECONDS = 10

_scheduler_task: asyncio.Task | None = None


async def _dispatch_due_posts() -> None:
    """One scheduler tick: find due SCHEDULED posts and send to their agent."""
    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Post).options(selectinload(Post.media_files))
            .where(Post.status == Post.STATUS_SCHEDULED, Post.scheduled_time <= now)
        )
        posts = result.scalars().all()

        # Group due posts by user so we can auto-start one agent per user.
        due_by_user: dict[int, list[Post]] = {}
        for post in posts:
            due_by_user.setdefault(post.user_id, []).append(post)

        for user_id, user_posts in due_by_user.items():
            # If the agent is offline, try to auto-start it. The launched
            # agent will connect over WebSocket, which triggers the
            # "agent-online" hook in the WebSocket handler and dispatches
            # the waiting posts to it.
            if not registry.is_online(user_id):
                await ensure_agent_running(user_id)
                continue

            for post in user_posts:
                media_urls = [
                    f"{settings.BASE_URL}{settings.MEDIA_URL_PREFIX}/{m.file}"
                    for m in post.media_files
                ]
                if not media_urls and post.media:
                    media_urls.append(
                        f"{settings.BASE_URL}{settings.MEDIA_URL_PREFIX}/{post.media}"
                    )

                sent = await registry.send_to_user(user_id, {
                    "type": "send_task",
                    "post_id": post.id,
                    "platform": post.platform,
                    "caption": post.caption,
                    "media": media_urls,
                })

                if sent:
                    post.status = Post.STATUS_PROCESSING
                    print(
                        f"[auto-scheduler] Dispatched post {post.id} "
                        f"({post.platform}) to agent for user {user_id}"
                    )

        await db.commit()


async def _scheduler_loop() -> None:
    """Infinite loop that ticks the scheduler every POLL_INTERVAL_SECONDS."""
    print(
        f"[auto-scheduler] Background scheduler started "
        f"(every {POLL_INTERVAL_SECONDS}s)"
    )
    while True:
        try:
            await _dispatch_due_posts()
        except asyncio.CancelledError:
            print("[auto-scheduler] Stopped.")
            raise
        except Exception as e:
            # Never let the loop die — just log and continue.
            print(f"[auto-scheduler] ERROR: Tick failed: {e}")
        await asyncio.sleep(POLL_INTERVAL_SECONDS)


def start_scheduler() -> None:
    """Start the background scheduler task (idempotent)."""
    global _scheduler_task
    if _scheduler_task is None or _scheduler_task.done():
        _scheduler_task = asyncio.create_task(_scheduler_loop())


async def stop_scheduler() -> None:
    """Cancel the background scheduler task on shutdown."""
    global _scheduler_task
    if _scheduler_task is not None:
        _scheduler_task.cancel()
        try:
            await _scheduler_task
        except asyncio.CancelledError:
            pass
        _scheduler_task = None