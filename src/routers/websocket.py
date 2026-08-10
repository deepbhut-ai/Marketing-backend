"""
WebSocket endpoint for agent connections — replaces Django Channels AgentConsumer.

Routes:
  /ws/agent/?token=...     (token-based, secure)
"""
import json
from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.core.config import settings
from src.core.database import AsyncSessionLocal
from src.core.websocket_manager import registry, hash_token
from src.models.accounts import AgentDevice
from src.models.posts import Post
from src.services.agent_starter import terminate_agent_for_user

router = APIRouter()


async def _maybe_close_agent(user_id: int) -> None:
    """Close the auto-started agent if no posts are left to process."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Post).where(
                Post.user_id == user_id,
                Post.status.in_([Post.STATUS_SCHEDULED, Post.STATUS_PROCESSING]),
            )
        )
        remaining = result.scalars().all()

    if not remaining:
        print(f"[ws] All tasks done for user {user_id}; closing agent console.")
        await terminate_agent_for_user(user_id)


async def _dispatch_waiting_posts_for_user(user_id: int, ws: WebSocket) -> None:
    """Send any due SCHEDULED posts for this user now that their agent is online."""
    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Post).options(selectinload(Post.media_files))
            .where(
                Post.user_id == user_id,
                Post.status == Post.STATUS_SCHEDULED,
                Post.scheduled_time <= now,
            )
        )
        posts = result.scalars().all()

        for post in posts:
            media_urls = [
                f"{settings.BASE_URL}{settings.MEDIA_URL_PREFIX}/{m.file}"
                for m in post.media_files
            ]
            if not media_urls and post.media:
                media_urls.append(
                    f"{settings.BASE_URL}{settings.MEDIA_URL_PREFIX}/{post.media}"
                )

            try:
                await ws.send_text(json.dumps({
                    "type": "send_task",
                    "post_id": post.id,
                    "platform": post.platform,
                    "caption": post.caption,
                    "media": media_urls,
                }))
                post.status = Post.STATUS_PROCESSING
                print(
                    f"[agent-online] Dispatched waiting post {post.id} "
                    f"({post.platform}) to agent for user {user_id}"
                )
            except Exception as e:
                print(f"[agent-online] ERROR: Failed to send post {post.id}: {e}")

        await db.commit()


@router.websocket("/ws/agent/")
async def agent_websocket(websocket: WebSocket):
    await websocket.accept()

    # Parse token from query string
    raw_token = websocket.query_params.get("token")
    if not raw_token:
        await websocket.close(code=4001, reason="No token provided")
        return

    token_hash = hash_token(raw_token)

    # Look up device
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(AgentDevice).where(AgentDevice.token_hash == token_hash, AgentDevice.is_active == True)
        )
        device = result.scalar_one_or_none()

    if not device:
        print("[ws] Invalid agent token")
        await websocket.close(code=4003, reason="Invalid agent token")
        return

    user_id = device.user_id
    group_name = f"agent_{user_id}"
    print(f"[ws] Agent joined group: {group_name}")

    # Register connection
    await registry.add(user_id, websocket)

    # Mark device online
    async with AsyncSessionLocal() as db:
        from datetime import datetime, timezone
        device.is_online = True
        device.last_seen = datetime.now(timezone.utc)
        await db.merge(device)
        await db.commit()

    # Agent just came online — dispatch any waiting due posts for this user
    await _dispatch_waiting_posts_for_user(user_id, websocket)

    try:
        while True:
            # Listen for messages from the agent (e.g. task_result)
            data = await websocket.receive_text()
            message = json.loads(data)

            if message.get("type") == "task_result":
                post_id = message.get("post_id")
                success = message.get("success", False)
                error_msg = message.get("message", "")

                # Update post status in DB
                async with AsyncSessionLocal() as db:
                    from sqlalchemy import select as sel
                    from src.models.posts import Post
                    result = await db.execute(sel(Post).where(Post.id == post_id))
                    post = result.scalar_one_or_none()
                    if post:
                        post.status = Post.STATUS_POSTED if success else Post.STATUS_FAILED
                        post.error_message = error_msg if not success else None
                        await db.commit()
                    print(f"[ws] Post {post_id} status -> {'posted' if success else 'failed'}")

                # If no more pending/processing posts remain for this user,
                # close the auto-started agent console window.
                await _maybe_close_agent(user_id)

    except WebSocketDisconnect:
        print(f"[ws] Agent disconnected from group {group_name}")
    except Exception as e:
        print(f"[ws] WebSocket error: {e}")
    finally:
        await registry.remove(user_id, websocket)
        # Mark device offline
        async with AsyncSessionLocal() as db:
            from datetime import datetime, timezone
            device.is_online = False
            await db.merge(device)
            await db.commit()