"""
Celery tasks for comments — replaces apps/comments/tasks.py.
"""
from celery import shared_task
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from src.core.config import settings
from src.core.websocket_manager import registry
from src.models.posts import Post
from src.models.comments import PostComment, CommentSettings


_sync_engine = None


def _get_sync_session() -> Session:
    global _sync_engine
    if _sync_engine is None:
        _sync_engine = create_engine(settings.DATABASE_SYNC_URL, pool_pre_ping=True)
    return Session(_sync_engine)


def _send_check_comments_task(post: Post):
    message = {
        "type": "send_check_comments",
        "post_id": post.id,
        "platform": post.platform,
        "post_url": post.post_url or "",
    }
    registry.send_to_user_sync(post.user_id, message)


@shared_task(name="src.celery_tasks.comments.check_post_comments")
def check_post_comments():
    """Check comments on all posted posts that have comment detection on."""
    session = _get_sync_session()
    try:
        posts = session.query(Post).filter(Post.status == Post.STATUS_POSTED).all()
        handled_users = set()

        for post in posts:
            settings_obj = session.query(CommentSettings).filter(
                CommentSettings.user_id == post.user_id
            ).first()

            if settings_obj and settings_obj.is_comment_detection_on:
                if not post.post_url:
                    print(f"⏭️ Skipping post {post.id}: post_url missing")
                    continue
                print(f"💬 Checking comments for post {post.id}")
                _send_check_comments_task(post)
            else:
                # When comment detection is OFF, run normal posting for this user
                # (matches Django behavior — apps/comments/tasks.py:35)
                if post.user_id not in handled_users:
                    print(f"⏭️ Comment detection OFF for user {post.user_id}. Running normal posting code instead.")
                    from src.celery_tasks.scheduler import check_scheduled_posts
                    check_scheduled_posts.delay(user_id=post.user_id)
                    handled_users.add(post.user_id)

        return "Comment check complete"
    finally:
        session.close()