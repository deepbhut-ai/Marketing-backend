"""
Celery tasks for scheduler — replaces apps/scheduler/tasks.py.

Uses a SYNC SQLAlchemy session (Celery workers are sync).
"""
from datetime import datetime, timezone

from celery import shared_task
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from src.core.config import settings
from src.core.websocket_manager import registry
from src.models.accounts import AgentDevice
from src.models.posts import Post
from src.models.post_media import PostMedia
from src.services.agent_starter import ensure_agent_running


_sync_engine = None


def _get_sync_session() -> Session:
    global _sync_engine
    if _sync_engine is None:
        _sync_engine = create_engine(settings.DATABASE_SYNC_URL, pool_pre_ping=True)
    return Session(_sync_engine)


def _send_task_to_agent(post: Post, session: Session):
    """Build media URLs and send task via WebSocket (sync wrapper around async)."""
    import asyncio

    media_urls = []
    for m in session.query(PostMedia).filter(PostMedia.post_id == post.id):
        media_urls.append(f"{settings.BASE_URL}{settings.MEDIA_URL_PREFIX}/{m.file}")
    if not media_urls and post.media:
        media_urls.append(f"{settings.BASE_URL}{settings.MEDIA_URL_PREFIX}/{post.media}")

    message = {
        "type": "send_task",
        "post_id": post.id,
        "platform": post.platform,
        "caption": post.caption,
        "media": media_urls,
    }

    # Try to send via the async registry. In a Celery worker (separate process),
    # the in-memory registry won't have the agent connection. For multi-process,
    # use Redis pubsub. For local single-process testing, this works if the
    # FastAPI app and Celery share the same process (rare).
    try:
        loop = asyncio.new_event_loop()
        sent = loop.run_until_complete(registry.send_to_user(post.user_id, message))
        loop.close()
        if not sent:
            print(f"⚠️ No agent online for user {post.user_id}. Post {post.id} will retry.")
        return sent
    except Exception as e:
        print(f"❌ Failed to send task to agent: {e}")
        return False


@shared_task(name="src.celery_tasks.scheduler.check_scheduled_posts")
def check_scheduled_posts(user_id: int = None):
    """Check for scheduled posts whose time has come and send to agent."""
    now = datetime.now(timezone.utc)
    session = _get_sync_session()
    try:
        query = session.query(Post).filter(
            Post.status == Post.STATUS_SCHEDULED,
            Post.scheduled_time <= now,
        )
        if user_id:
            query = query.filter(Post.user_id == user_id)

        posts = query.all()
        count = len(posts)

        sent_count = 0
        # Group by user so we auto-start one agent per user (not per post).
        started_users: set[int] = set()
        for post in posts:
            print(f"🚀 Sending post {post.id} ({post.platform}) to agent")
            sent = _send_task_to_agent(post, session)
            if sent:
                post.status = Post.STATUS_PROCESSING
                session.commit()
                sent_count += 1
            else:
                # Agent offline — try to auto-start the agent for this user.
                # The launched agent connects to the FastAPI server over
                # WebSocket; the in-process scheduler (running in FastAPI)
                # will then dispatch the waiting posts to it. This Celery
                # task can't reach the agent directly (separate process),
                # but it can spawn the agent process so it connects back.
                uid = post.user_id
                if uid not in started_users:
                    started_users.add(uid)
                    import asyncio
                    try:
                        asyncio.run(ensure_agent_running(uid))
                    except Exception as e:
                        print(f"❌ auto-start agent for user {uid} failed: {e}")
                print(f"⚠️ No agent online for post {post.id}. Will retry.")

        return f"Sent {sent_count} of {count} posts to agent"
    finally:
        session.close()