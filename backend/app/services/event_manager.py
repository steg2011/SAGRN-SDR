import asyncio
import json
from typing import AsyncGenerator, Dict, Any, Set
from datetime import datetime


class EventManager:
    """Manages Server-Sent Events for real-time updates"""

    def __init__(self):
        self._subscribers: Set[asyncio.Queue] = set()
        self._lock = asyncio.Lock()

    async def subscribe(self) -> AsyncGenerator[str, None]:
        """Subscribe to events and yield SSE-formatted messages"""
        queue: asyncio.Queue = asyncio.Queue()

        async with self._lock:
            self._subscribers.add(queue)

        try:
            # Send initial connection event
            yield self._format_sse("connected", {"timestamp": datetime.utcnow().isoformat()})

            while True:
                try:
                    # Wait for events with timeout to send keepalive
                    event = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield event
                except asyncio.TimeoutError:
                    # Send keepalive comment to prevent connection timeout
                    yield ": keepalive\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            async with self._lock:
                self._subscribers.discard(queue)

    async def broadcast(self, event_type: str, data: Dict[str, Any]):
        """Broadcast an event to all subscribers"""
        message = self._format_sse(event_type, data)

        async with self._lock:
            for queue in self._subscribers:
                try:
                    queue.put_nowait(message)
                except asyncio.QueueFull:
                    pass  # Skip slow consumers

    def _format_sse(self, event_type: str, data: Dict[str, Any]) -> str:
        """Format data as Server-Sent Event"""
        json_data = json.dumps(data, default=str)
        return f"event: {event_type}\ndata: {json_data}\n\n"

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)


# Singleton instance
_event_manager: EventManager | None = None


def get_event_manager() -> EventManager:
    """Get the singleton event manager instance"""
    global _event_manager
    if _event_manager is None:
        _event_manager = EventManager()
    return _event_manager
