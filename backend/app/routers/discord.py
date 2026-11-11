"""The Discord bot's web side (SPEC 19): the endpoint Discord sends commands and button clicks to,
adding the bot to a group's server, linking Discord accounts, and "Sign in with Discord".

The OAuth `state` is signed and tied to a short-lived cookie in the browser that started it, so a
link from someone else can't attach their Discord (or their server) to your account or group.
"""

import base64
import hashlib
import hmac
import json
import logging
import secrets
import time
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.config import get_settings
from app.db import get_session
from app.models import DiscordLink, DiscordMessage, User
from app.routers.access import Ctx, current_ctx, current_user, optional_user, require_owner
from app.services import auth, discord_bot
from app.services import discord_render as render
from app.services.discord_api import DiscordClient, DiscordError, authorize_url, verify

log = logging.getLogger("uvicorn.error")
router = APIRouter(prefix="/api/discord", tags=["discord"])

STATE_COOKIE = "hd_discord"
STATE_SECONDS = 600
MAX_SKEW = 300  # reject interactions signed more than 5 minutes ago (replays)


_client: DiscordClient | None = None


def get_discord_client() -> DiscordClient:
    """One shared client (connection pool) for the site's requests. Tests swap in a fake."""
    global _client
    if _client is None:
        _client = DiscordClient()
    return _client


def _enabled() -> None:
    if not get_settings().discord_enabled:
        raise HTTPException(404, "The Discord bot isn't set up on this site")


def _redirect_uri(request: Request) -> str:
    base = get_settings().public_url.rstrip("/") or str(request.base_url).rstrip("/")
    return f"{base}/api/discord/callback"


# --- signed OAuth state ----------------------------------------------------------------------------


def _key() -> bytes:
    return hashlib.sha256(b"hardcore-draft-discord-state:" + get_settings().discord_client_secret.encode()).digest()


def _make_state(purpose: str, nonce: str, user_id: int | None = None, group_id: int | None = None) -> str:
    body = json.dumps({"p": purpose, "u": user_id, "g": group_id, "n": nonce, "e": int(time.time()) + STATE_SECONDS}, separators=(",", ":"))
    raw = base64.urlsafe_b64encode(body.encode()).decode().rstrip("=")
    sig = hmac.new(_key(), raw.encode(), hashlib.sha256).hexdigest()
    return f"{raw}.{sig}"


def _read_state(state: str, nonce: str | None) -> dict | None:
    try:
        raw, sig = state.rsplit(".", 1)
    except ValueError:
        return None
    if not hmac.compare_digest(sig, hmac.new(_key(), raw.encode(), hashlib.sha256).hexdigest()):
        return None
    data = json.loads(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)))
    if data["e"] < time.time() or not nonce or not hmac.compare_digest(data["n"], nonce):
        return None
    return data


def _start(request: Request, purpose: str, install: bool = False, user_id: int | None = None, group_id: int | None = None) -> RedirectResponse:
    nonce = secrets.token_urlsafe(16)
    response = RedirectResponse(authorize_url(_redirect_uri(request), _make_state(purpose, nonce, user_id, group_id), install), 302)
    response.set_cookie(
        STATE_COOKIE, nonce, max_age=STATE_SECONDS, httponly=True, samesite="lax", secure=request.url.scheme == "https", path="/api/discord"
    )
    return response


# --- interactions (slash commands, buttons, menus) ----------------------------------------------------


@router.post("/interactions")
async def interactions(
    request: Request,
    background: BackgroundTasks,
    session: Session = Depends(get_session),
    client=Depends(get_discord_client),
):
    _enabled()
    body = await request.body()
    signature = request.headers.get("X-Signature-Ed25519", "")
    timestamp = request.headers.get("X-Signature-Timestamp", "")
    if not verify(get_settings().discord_public_key, signature, timestamp, body):
        raise HTTPException(401, "Bad signature")
    if not timestamp.isdigit() or abs(time.time() - int(timestamp)) > MAX_SKEW:
        raise HTTPException(401, "Too old")
    data = json.loads(body)
    answer = discord_bot.handle(session, data)
    if answer.followup is not None:
        bind = session.get_bind()
        token = data["token"]

        async def fill_in():
            try:
                message = await answer.followup(lambda: Session(bind))
            except Exception:  # noqa: BLE001 - tell the person rather than leave "thinking..." forever
                log.exception("Discord follow-up failed")
                message = render.reply("Something went wrong. Try again in a moment.")
            try:
                await client.edit_reply(token, message)
            except DiscordError as e:
                log.warning("Couldn't fill in a Discord reply: %s", e)

        background.add_task(fill_in)
    return JSONResponse(answer.response)


# --- status for the Settings page ------------------------------------------------------------------


@router.get("")
def status(ctx: Ctx = Depends(current_ctx), session: Session = Depends(get_session)):
    """Whether the bot is set up, whether you linked your Discord, and (group owner) the server."""
    enabled = get_settings().discord_enabled
    out: dict = {"enabled": enabled, "linked": ctx.user.discord_id is not None, "server": None, "kinds": discord_bot.KINDS}
    if enabled and ctx.group is not None:
        link = session.exec(select(DiscordLink).where(DiscordLink.group_id == ctx.group_id)).first()
        if link is not None:
            out["server"] = {
                "guild_name": link.guild_name,
                "channel_id": link.channel_id,
                "muted": link.muted,
                "last_error": link.last_error,
            }
    return out


@router.get("/available")
def available():
    """Signed out: whether to show "Sign in with Discord"."""
    return {"enabled": get_settings().discord_enabled}


# --- linking an account, signing in --------------------------------------------------------------------


@router.get("/connect")
def connect(request: Request, user: User = Depends(current_user)):
    """Link your Discord account (Settings): the bot then knows who you are."""
    _enabled()
    return _start(request, "link", user_id=user.id)


@router.delete("/account", status_code=204)
def unlink_account(user: User = Depends(current_user), session: Session = Depends(get_session)):
    user.discord_id = None
    session.add(user)
    session.commit()


@router.get("/login")
def login(request: Request, user: User | None = Depends(optional_user)):
    """Sign in with a Discord account that's already linked to a Hardcore Draft account."""
    _enabled()
    if user is not None:
        return RedirectResponse("/", 302)
    return _start(request, "login")


# --- adding the bot to the group's server (group owner) ----------------------------------------------


@router.get("/install")
def install(request: Request, ctx: Ctx = Depends(require_owner)):
    _enabled()
    return _start(request, "install", install=True, user_id=ctx.user.id, group_id=ctx.group_id)


@router.get("/callback")
async def callback(
    request: Request,
    session: Session = Depends(get_session),
    client=Depends(get_discord_client),
    code: str | None = None,
    state: str = "",
    guild_id: str | None = None,
    error: str | None = None,
):
    """Where Discord sends the browser back after its consent page."""
    _enabled()
    data = _read_state(state, request.cookies.get(STATE_COOKIE))
    purpose = (data or {}).get("p")
    fail = "/login" if purpose == "login" else "/settings"

    def back(path: str, **params) -> RedirectResponse:
        query = "&".join(f"{k}={v}" for k, v in params.items())
        response = RedirectResponse(f"{path}?{query}#discord" if query else path, 302)
        response.delete_cookie(STATE_COOKIE, path="/api/discord")
        return response

    if data is None:
        return back(fail, discord_error="expired")
    if error or not code:
        return back(fail, discord_error="cancelled")
    try:
        token = await client.exchange(code, _redirect_uri(request))
        me = await client.me(token["access_token"]) if "identify" in token.get("scope", "") else None
    except DiscordError as e:
        log.warning("Discord sign-in failed: %s", e)
        return back(fail, discord_error="discord")
    discord_id = str(me["id"]) if me else None

    if purpose == "login":
        user = session.exec(select(User).where(User.discord_id == discord_id)).first() if discord_id else None
        if user is None:
            return back("/login", discord_error="not-linked")
        from app.routers.account import _sign_in

        response = back("/")
        _sign_in(request, response, session, user)
        return response

    user = session.get(User, data["u"]) if data.get("u") else None
    if user is None:
        return back("/login", discord_error="expired")

    def link_user() -> str | None:
        """Attach this Discord account to the user; "taken" if another account has it."""
        if not discord_id or user.discord_id == discord_id:
            return None
        other = session.exec(select(User).where(User.discord_id == discord_id)).first()
        if other is not None:
            return "taken"
        user.discord_id = discord_id
        session.add(user)
        return None

    if purpose == "link":
        problem = link_user()
        session.commit()
        return back("/settings", discord_error=problem) if problem else back("/settings", discord="linked")

    # purpose == "install"
    group_id = data.get("g")
    member = auth.membership(session, group_id, user.id) if group_id else None
    if member is None or member.role != "owner":
        return back("/settings", discord_error="not-owner")
    guild = token.get("guild") or {}
    guild_id = str(guild.get("id") or guild_id or "")
    if not guild_id:
        return back("/settings", discord_error="no-server")
    taken = session.exec(select(DiscordLink).where(DiscordLink.guild_id == guild_id)).first()
    if taken is not None and taken.group_id != group_id:
        return back("/settings", discord_error="server-taken")
    link = session.exec(select(DiscordLink).where(DiscordLink.group_id == group_id)).first()
    if link is None:
        link = DiscordLink(group_id=group_id, guild_id=guild_id)
    elif link.guild_id != guild_id:
        _forget_messages(session, group_id)
        link.guild_id, link.channel_id = guild_id, None
    link.guild_name = guild.get("name") or link.guild_name
    link.channel_id = link.channel_id or (str(guild["system_channel_id"]) if guild.get("system_channel_id") else None)
    link.installed_by_user_id = user.id
    link.last_error = None
    discord_bot.seed_announced(session, link)
    session.add(link)
    link_user()  # the owner's own Discord comes along, if it's free
    session.commit()
    return back("/settings", discord="server")


def _forget_messages(session: Session, group_id: int) -> None:
    for m in session.exec(select(DiscordMessage).where(DiscordMessage.group_id == group_id)).all():
        session.delete(m)


# --- the group's server (group owner) ----------------------------------------------------------------


def _link(session: Session, ctx: Ctx) -> DiscordLink:
    _enabled()
    link = session.exec(select(DiscordLink).where(DiscordLink.group_id == ctx.group_id)).first()
    if link is None:
        raise HTTPException(404, "Add the bot to your Discord server first")
    return link


@router.get("/channels")
async def channels(ctx: Ctx = Depends(require_owner), session: Session = Depends(get_session), client=Depends(get_discord_client)):
    link = _link(session, ctx)
    guild_id = link.guild_id
    session.commit()  # don't hold the database while waiting on Discord
    try:
        rows = await client.channels(guild_id)
    except DiscordError as e:
        raise HTTPException(502, "Couldn't read the server's channels. Is the bot still in it?") from e
    return sorted(rows, key=lambda c: c["position"])


class ServerPatch(BaseModel):
    channel_id: str | None = None
    muted: list[Literal["spins", "live", "results", "moments", "recaps", "nudges", "daily"]] | None = Field(default=None, max_length=7)


@router.patch("/server")
async def update_server(
    body: ServerPatch, ctx: Ctx = Depends(require_owner), session: Session = Depends(get_session), client=Depends(get_discord_client)
):
    link = _link(session, ctx)
    if body.channel_id is not None:
        guild_id = link.guild_id
        session.commit()
        try:
            ids = {c["id"] for c in await client.channels(guild_id)}
        except DiscordError as e:
            raise HTTPException(502, "Couldn't read the server's channels. Is the bot still in it?") from e
        if body.channel_id not in ids:
            raise HTTPException(422, "Pick a text channel in your server")
        link = _link(session, ctx)
        link.channel_id = body.channel_id
        link.last_error = None
    if body.muted is not None:
        link.muted = sorted(set(body.muted))
    session.add(link)
    session.commit()
    return status(ctx, session)


@router.post("/test", status_code=204)
async def test_message(ctx: Ctx = Depends(require_owner), session: Session = Depends(get_session), client=Depends(get_discord_client)):
    link = _link(session, ctx)
    if not link.channel_id:
        raise HTTPException(409, "Pick a channel first")
    channel_id, group_name = link.channel_id, ctx.group.name
    session.commit()
    try:
        await client.post(channel_id, render.reply(f"Hardcore Draft is set up for **{group_name}**. Spins and results will show up here."))
    except DiscordError as e:
        raise HTTPException(502, f"Discord refused the message: {e}") from e


@router.delete("/server", status_code=204)
async def unlink_server(ctx: Ctx = Depends(require_owner), session: Session = Depends(get_session), client=Depends(get_discord_client)):
    """Remove the bot from the server and forget it."""
    link = _link(session, ctx)
    guild_id = link.guild_id
    _forget_messages(session, ctx.group_id)
    session.delete(link)
    session.commit()
    try:
        await client.leave(guild_id)
    except DiscordError as e:
        log.info("Bot couldn't leave server %s (maybe already removed): %s", guild_id, e)
