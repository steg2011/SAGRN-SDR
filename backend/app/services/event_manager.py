import asyncio
import json
import time
from typing import AsyncGenerator, Dict, Any
from datetime import datetime
import redis.asyncio as redis

CHANNEL = "sagrn:events"

# Max SSE connection lifetime (seconds). Close before Cloudflare kills it
# so the browser gets a clean disconnect and reconnects gracefully.
SSE_MAX_LIFETIME = 55


class EventManager:
    """Manages Server-Sent Events via Redis Pub/Sub"""

    def __init__(self, redis_url: str):
        self._redis_url = redis_url
        self._redis: redis.Redis | None = None

    async def _get_redis(self) -> redis.Redis:
        if self._redis is None:
            self._redis = redis.from_url(
                self._redis_url,
                decode_responses=True
            )
        return self._redis

    async def subscribe(self) -> AsyncGenerator[str, None]:
        """Subscribe to events and yield SSE-formatted messages.

        Connection closes after SSE_MAX_LIFETIME seconds to prevent
        zombie connections when behind Cloudflare Tunnel.
        """
        r = await self._get_redis()
        pubsub = r.pubsub()
        await pubsub.subscribe(CHANNEL)
        start_time = time.monotonic()

        try:
            # Send initial connection event with retry hint for the browser
            yield self._format_sse("connected", {"timestamp": datetime.utcnow().isoformat()})

            while True:
                # Check max lifetime - close gracefully so EventSource reconnects
                if time.monotonic() - start_time > SSE_MAX_LIFETIME:
                    break

                try:
                    message = await asyncio.wait_for(
                        pubsub.get_message(
                            ignore_subscribe_messages=True,
                            timeout=1.0
                        ),
                        timeout=10.0
                    )
                    if message and message["type"] == "message":
                        yield message["data"]
                    elif message is None:
                        continue
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            await pubsub.unsubscribe(CHANNEL)
            await pubsub.close()

    async def broadcast(self, event_type: str, data: Dict[str, Any]):
        """Broadcast an event to all subscribers via Redis"""
        r = await self._get_redis()
        message = self._format_sse(event_type, data)
        await r.publish(CHANNEL, message)

    def _format_sse(self, event_type: str, data: Dict[str, Any]) -> str:
        """Format data as Server-Sent Event"""
        json_data = json.dumps(data, default=str)
        return f"event: {event_type}\ndata: {json_data}\n\n"

    @property
    async def subscriber_count(self) -> int:
        r = await self._get_redis()
        info = await r.pubsub_numsub(CHANNEL)
        return info.get(CHANNEL, 0) if isinstance(info, dict) else 0

    async def close(self):
        if self._redis:
            await self._redis.close()
            self._redis = None


# Singleton instance
_event_manager: EventManager | None = None


def get_event_manager() -> EventManager:
    """Get the singleton event manager instance"""
    global _event_manager
    if _event_manager is None:
        from app.core.config import get_settings
        settings = get_settings()
        _event_manager = EventManager(settings.redis_url)
    return _event_manager
