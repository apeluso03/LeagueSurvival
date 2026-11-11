"""Live updates (SPEC 12.3): push what changed to every browser looking at a group.

- Browsers keep one WebSocket open (routers/live_updates.py) and subscribe to their group here.
- The game rules' events (services/events.emit) are pushed once their transaction commits, so a
  browser never hears about a change that was rolled back. Any other successful change made
  through the API (a purchase, a settings change, a new player) sends a plain "changed".
- Messages carry only the event type and ids; browsers refetch what they're allowed to see.
- Each message names the browser tab that caused it (the X-Client-Id header), so that tab can
  skip what it already knows (it plays its own spin's reels already).

Everything lives in this process's memory: the site runs as one instance (railway.json). Running
several would need a shared channel such as Postgres LISTEN/NOTIFY or Redis.
"""

import asyncio
import contextvars
import logging

from sqlalchemy import event
from sqlalchemy.orm import Session

log = logging.getLogger("uvicorn.error")

# The browser tab behind the current request (set by LiveUpdatesMiddleware).
ORIGIN: contextvars.ContextVar[str | None] = contextvars.ContextVar("live_origin", default=None)
QUEUE_SIZE = 100  # a browser that falls this far behind misses messages (it refreshes on reconnect)
PAYLOAD_KEYS = ("game_id", "run_id")  # ids only: nothing private goes over the socket


class Hub:
    def __init__(self) -> None:
        self._subs: dict[int, set[asyncio.Queue]] = {}
        self._loop: asyncio.AbstractEventLoop | None = None

    def subscribe(self, group_id: int) -> asyncio.Queue:
        """Call from the event loop. The queue gets every message for the group until unsubscribed."""
        self._loop = asyncio.get_running_loop()
        q: asyncio.Queue = asyncio.Queue(QUEUE_SIZE)
        self._subs.setdefault(group_id, set()).add(q)
        return q

    def unsubscribe(self, group_id: int, q: asyncio.Queue) -> None:
        subs = self._subs.get(group_id)
        if subs is not None:
            subs.discard(q)
            if not subs:
                del self._subs[group_id]

    def listeners(self, group_id: int) -> int:
        return len(self._subs.get(group_id, ()))

    def publish(self, group_id: int, message: dict) -> None:
        """Send to everyone watching the group. Safe from any thread (request handlers run in a pool)."""
        if self._loop is None or group_id not in self._subs:
            return

        def put() -> None:
            for q in list(self._subs.get(group_id, ())):
                try:
                    q.put_nowait(message)
                except asyncio.QueueFull:
                    pass  # that browser is stuck; it catches up when it reconnects

        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        try:
            if running is self._loop:
                put()
            else:
                self._loop.call_soon_threadsafe(put)
        except RuntimeError:  # the loop is closed (shutting down, or between tests)
            self._loop = None


hub = Hub()


def message(type_: str, payload: dict | None = None, origin: str | None = None) -> dict:
    out = {"type": type_, "origin": origin}
    for k in PAYLOAD_KEYS:
        if payload and payload.get(k) is not None:
            out[k] = payload[k]
    return out


def queue_event(session: Session, group_id: int, type_: str, payload: dict) -> None:
    """Push this event once the session's transaction commits (services/events.emit calls it)."""
    session.info.setdefault("live_events", []).append((group_id, type_, payload))


@event.listens_for(Session, "after_commit")
def _after_commit(session: Session) -> None:
    pending = session.info.pop("live_events", None)
    if not pending:
        return
    origin = ORIGIN.get()
    for group_id, type_, payload in pending:
        hub.publish(group_id, message(type_, payload, origin))


@event.listens_for(Session, "after_rollback")
def _after_rollback(session: Session) -> None:
    session.info.pop("live_events", None)


class LiveUpdatesMiddleware:
    """Remembers which browser tab sent a request (for the events it causes), and after any
    successful change made through the API, tells the group's other browsers to refresh."""

    SAFE = {"GET", "HEAD", "OPTIONS"}

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not scope["path"].startswith("/api/") or scope["method"] in self.SAFE:
            await self.app(scope, receive, send)
            return
        origin = None
        for k, v in scope.get("headers", []):
            if k == b"x-client-id":
                origin = v.decode("latin-1")[:64] or None
                break
        status = 500
        holder: dict = {}
        scope["live_updates"] = holder  # routers/access.current_ctx notes the group here

        async def send_(msg):
            nonlocal status
            if msg["type"] == "http.response.start":
                status = msg["status"]
            await send(msg)

        token = ORIGIN.set(origin)
        try:
            await self.app(scope, receive, send_)
        finally:
            ORIGIN.reset(token)
        group_id = holder.get("group_id")
        if group_id is not None and status < 400:
            hub.publish(group_id, message("changed", origin=origin))
