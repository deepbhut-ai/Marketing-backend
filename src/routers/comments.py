"""Comments router — generate-reply."""
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.websocket_manager import registry
from src.dependencies.auth import get_current_user
from src.models.accounts import User
from src.models.posts import Post
from src.models.comments import PostComment, CommentSettings
from src.services.ai_reply import generate_ai_reply

router = APIRouter(prefix="/comments", tags=["comments"])


@router.post("/generate-reply/")
async def generate_reply_api(
    data: dict,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    post_id = data.get("post_id")
    mode = data.get("mode", "AI").upper()

    if mode not in ["AI", "MANUAL"]:
        return {"success": False, "message": "mode must be AI or MANUAL"}, 400
    if not post_id:
        return {"success": False, "message": "post_id required"}, 400

    result = await db.execute(select(Post).where(Post.id == post_id))
    post = result.scalar_one_or_none()
    if not post:
        return {"success": False, "message": "Post not found"}, 404

    comment_result = await db.execute(
        select(PostComment)
        .where(PostComment.post_id == post.id, PostComment.status == PostComment.STATUS_NEW,
               PostComment.reply_text.is_(None))
        .order_by(PostComment.created_at.desc())
    )
    comment = comment_result.scalars().first()

    if not comment:
        return {"success": False, "message": "No comments found on this post"}, 404

    # Get or create settings
    settings_result = await db.execute(select(CommentSettings).where(CommentSettings.user_id == post.user_id))
    settings_obj = settings_result.scalar_one_or_none()
    if not settings_obj:
        settings_obj = CommentSettings(user_id=post.user_id)
        db.add(settings_obj)
        await db.flush()

    result = generate_ai_reply(
        comment_text=comment.comment_text,
        author=comment.comment_author or "",
        post_caption=post.caption,
        previous_comments="",
        platform=post.platform,
        mode=mode,
        tone=settings_obj.tone,
        keyword_replies=settings_obj.keyword_replies,
        default_reply=settings_obj.default_reply,
    )

    if not result.get("should_reply"):
        comment.status = PostComment.STATUS_IGNORED
        await db.flush()
        return {"success": True, "message": "Comment ignored by AI"}

    reply_text = result["reply"]
    comment.reply_text = reply_text
    comment.status = PostComment.STATUS_REPLY_PENDING
    await db.flush()

    await registry.send_to_user(post.user_id, {
        "type": "send_reply_comment",
        "comment_id": comment.id,
        "platform": post.platform,
        "reply_text": reply_text,
        "post_url": post.post_url,
        "author": comment.comment_author,
        "comment_text": comment.comment_text,
    })

    return {"success": True, "message": "Reply sent to agent", "reply": reply_text}