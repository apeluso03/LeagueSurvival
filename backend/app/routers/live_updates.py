"""The live-updates WebSocket (SPEC 12.3, services/hub.py).

A signed-in browser connects to /api/ws and hears about every change in the group it's viewing:
`{"type": "spin" | "picks" | "result" | "undo" | "gold" | "revive" | "game_found" | "run_end" |
"changed", "game_id"?, "run_id"?, "origin"}`, plus a "ping" every 25 seconds. The session is
checked again on every ping: signing out or switching groups closes the socket, and the browser
reconnects to the right group.
"""

import asyncio
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlmodel import Session

from app.config import get_settings
from app.db import get_session
from app.services import auth
from app.services.hub import hub

router = APIRouter(tags=["live updates"])

PING_SECONDS = 25
SIGNED_OUT = 4401  # close codes the browser reads: 4401 = sign in again, 4409 = group changed
MOVED = 4409


def _same_site(ws: WebSocket) -> bool:
    """Only pages on this site (or the dev server and CORS origins) may open the socket."""
    origin = ws.headers.get("origin")
    if not origin:
        return True  # not a browser
    host = ws.headers.get("host", "")
    if urlsplit(origin).netloc == host:
        return True
    return origin.rstrip("/") in {o.rstrip("/") for o in get_settings().cors_origin_list}


def _group_for(session: Session, token: str | None) -> int | None:
    """The group this browser is viewing, if it's still signed in and a member."""
    row = auth.session_for_token(session, token)
    if row is None:
        return None
    if row.group_id and auth.membership(session, row.group_id, row.user_id):
        return row.group_id
    first = next(iter(auth.memberships(session, row.user_id)), None)
    return first.group_id if first else None


@router.websocket("/api/ws")
async def live_socket(ws: WebSocket, session: Session = Depends(get_session)):
    token = ws.cookies.get(auth.SESSION_COOKIE)
    if not _same_site(ws):
        await ws.close(code=1008)
        return
    group_id = _group_for(session, token)
    session.close()  # don't hold a connection for the whole socket
    if group_id is None:
        await ws.close(code=SIGNED_OUT)
        return
    await ws.accept()
    q = hub.subscribe(group_id)

    async def pump() -> int:
        await ws.send_json({"type": "hello", "group_id": group_id})
        while True:
            try:
                msg = await asyncio.wait_for(q.get(), PING_SECONDS)
            except TimeoutError:
                now = _group_for(session, token)
                session.close()
                if now != group_id:
                    return SIGNED_OUT if now is None else MOVED
                msg = {"type": "ping"}
            await ws.send_json(msg)

    async def drain() -> None:
        while True:
            await ws.receive_text()  # the browser sends nothing we need; this notices it leaving

    tasks = [asyncio.create_task(pump()), asyncio.create_task(drain())]
    try:
        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        finished = next(iter(done))
        if finished is tasks[0] and not finished.cancelled() and finished.exception() is None:
            await ws.close(code=finished.result())
    except WebSocketDisconnect:
        pass
    finally:
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        hub.unsubscribe(group_id, q)
