"""
WebSocket connection manager — replaces Django Channels' group_send.

Each agent connects via `/ws/agent/?token=...`. We authenticate by the
agent token hash, then keep a reference to the WebSocket so the scheduler
can push tasks to it.

For multi-process deployments, use Redis pubsub to broadcast. For single-
process (local dev), this in-memory dict is sufficient.
"""
import asyncio
import hashlib
from dataclasses import dataclass, field
from typing import Any

from fastapi import WebSocket


@dataclass
class _ConnectionRegistry:
    """Maps user_id → set of active WebSocket connections for that user's agents."""
    connections: dict[int, set[WebSocket]] = field(default_factory=dict)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def add(self, user_id: int, ws: WebSocket) -> None:
        async with self._lock:
            self.connections.setdefault(user_id, set()).add(ws)

    async def remove(self, user_id: int, ws: WebSocket) -> None:
        async with self._lock:
            conns = self.connections.get(user_id)
            if conns:
                conns.discard(ws)
                if not conns:
                    del self.connections[user_id]

    async def send_to_user(self, user_id: int, message: dict[str, Any]) -> bool:
        """Send a JSON message to all agents belonging to a user.

        Returns True if at least one agent received it.
        """
        import json
        async with self._lock:
            conns = list(self.connections.get(user_id, set()))
        if not conns:
            return False
        payload = json.dumps(message)
        for ws in conns:
            try:
                await ws.send_text(payload)
            except Exception:
                pass
        return True

    def is_online(self, user_id: int) -> bool:
        return bool(self.connections.get(user_id))

    def send_to_user_sync(self, user_id: int, message: dict[str, Any]) -> bool:
        """Sync wrapper for Celery tasks. Creates a new event loop.

        NOTE: In a multi-process deployment (Celery worker ≠ FastAPI process),
        the in-memory registry will be empty in the worker. Use Redis pubsub
        to broadcast across processes. For local single-process dev this works.
        """
        import asyncio
        import json
        try:
            loop = asyncio.new_event_loop()
            result = loop.run_until_complete(self.send_to_user(user_id, message))
            loop.close()
            return result
        except Exception as e:
            print(f"❌ send_to_user_sync failed: {e}")
            return False


# Singleton registry
registry = _ConnectionRegistry()


def hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode()).hexdigest()