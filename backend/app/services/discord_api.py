"""Talking to Discord (SPEC 19): its REST API with the bot token, OAuth for linking accounts and
adding the bot to a server, and checking the signature on requests Discord sends us.

The bot never connects to Discord's live gateway: slash commands and button clicks arrive as HTTPS
requests (routers/discord.py), and everything the bot posts goes out through REST.
"""

import asyncio
import json
import logging
from urllib.parse import urlencode

import httpx
from nacl.exceptions import BadSignatureError
from nacl.signing import VerifyKey

from app.config import get_settings

log = logging.getLogger("uvicorn.error")

API = "https://discord.com/api/v10"
AUTHORIZE_URL = "https://discord.com/oauth2/authorize"

# What the bot may do in a server: view channels, send messages, embed links, attach files.
# Nothing like manage server or read message history (SPEC 19.7).
BOT_PERMISSIONS = (1 << 10) | (1 << 11) | (1 << 14) | (1 << 15)
TEXT_CHANNELS = (0, 5)  # text, announcement

EPHEMERAL = 1 << 6  # a reply only the person who asked can see


class DiscordError(Exception):
    def __init__(self, status: int, message: str, code: int | None = None):
        super().__init__(f"Discord {status}: {message}")
        self.status = status
        self.code = code

    @property
    def lost_access(self) -> bool:
        """The bot was removed, the channel deleted, or it may not post there."""
        return self.status in (403, 404)


def verify(public_key: str, signature: str, timestamp: str, body: bytes) -> bool:
    """True if Discord signed this request (Ed25519 over timestamp + body)."""
    try:
        VerifyKey(bytes.fromhex(public_key)).verify(timestamp.encode() + body, bytes.fromhex(signature))
        return True
    except (BadSignatureError, ValueError):
        return False


def authorize_url(redirect_uri: str, state: str, install: bool = False) -> str:
    """Discord's consent page: link an account (identify) or add the bot to a server."""
    s = get_settings()
    params = {"client_id": s.discord_app_id, "response_type": "code", "redirect_uri": redirect_uri, "state": state}
    if install:
        params |= {"scope": "bot applications.commands identify", "permissions": str(BOT_PERMISSIONS)}
    else:
        params |= {"scope": "identify", "prompt": "none"}
    return f"{AUTHORIZE_URL}?{urlencode(params)}"


def _body(message: dict, files: list[tuple[str, bytes]] | None) -> dict:
    """A message as JSON, or with files as a multipart upload (the JSON goes in `payload_json`)."""
    if not files:
        return {"json": message}
    payload = {**message, "attachments": [{"id": i, "filename": name} for i, (name, _) in enumerate(files)]}
    return {
        "data": {"payload_json": json.dumps(payload)},
        "files": {f"files[{i}]": (name, content, "image/gif" if name.endswith(".gif") else "application/octet-stream") for i, (name, content) in enumerate(files)},
    }


class DiscordClient:
    """The REST calls the bot makes. Tests swap in a fake with the same methods."""

    def __init__(self, http: httpx.AsyncClient | None = None):
        s = get_settings()
        self.app_id = s.discord_app_id
        self._token = s.discord_bot_token
        self._secret = s.discord_client_secret
        self._http = http or httpx.AsyncClient(timeout=15)

    async def aclose(self) -> None:
        await self._http.aclose()

    async def _request(self, method: str, path: str, *, bot: bool = True, retries: int = 2, **kw):
        headers = kw.pop("headers", {})
        if bot:
            headers["Authorization"] = f"Bot {self._token}"
        for _ in range(retries + 1):
            res = await self._http.request(method, f"{API}{path}", headers=headers, **kw)
            if res.status_code == 429:  # rate limited: wait as long as Discord says, then retry
                wait = float((res.json() if res.content else {}).get("retry_after", 1))
                await asyncio.sleep(min(wait, 30))
                continue
            if res.status_code >= 400:
                try:
                    data = res.json()
                except ValueError:
                    data = {}
                raise DiscordError(res.status_code, data.get("message", res.text[:200]), data.get("code"))
            return res.json() if res.content else None
        raise DiscordError(429, "Still rate limited")

    # --- messages ---

    async def post(self, channel_id: str, message: dict, files: list[tuple[str, bytes]] | None = None) -> str:
        data = await self._request("POST", f"/channels/{channel_id}/messages", **_body(message, files))
        return data["id"]

    async def edit(self, channel_id: str, message_id: str, message: dict) -> None:
        await self._request("PATCH", f"/channels/{channel_id}/messages/{message_id}", json=message)

    async def edit_reply(self, interaction_token: str, message: dict, files: list[tuple[str, bytes]] | None = None) -> None:
        """Fill in a reply that was first answered with "thinking..." (a deferred interaction)."""
        path = f"/webhooks/{self.app_id}/{interaction_token}/messages/@original"
        await self._request("PATCH", path, bot=False, **_body(message, files))

    async def followup(self, interaction_token: str, message: dict) -> None:
        """Another message in answer to the same command (after its first reply)."""
        await self._request("POST", f"/webhooks/{self.app_id}/{interaction_token}", bot=False, json=message)

    # --- servers ---

    async def channels(self, guild_id: str) -> list[dict]:
        rows = await self._request("GET", f"/guilds/{guild_id}/channels")
        return [{"id": c["id"], "name": c["name"], "position": c.get("position", 0)} for c in rows if c.get("type") in TEXT_CHANNELS]

    async def leave(self, guild_id: str) -> None:
        await self._request("DELETE", f"/users/@me/guilds/{guild_id}")

    async def set_commands(self, commands: list[dict]) -> None:
        """Replace the bot's slash commands everywhere (idempotent)."""
        await self._request("PUT", f"/applications/{self.app_id}/commands", json=commands)

    # --- OAuth ---

    async def exchange(self, code: str, redirect_uri: str) -> dict:
        """Trade the code from Discord's consent page for a token (and, when adding the bot, the server)."""
        return await self._request(
            "POST",
            "/oauth2/token",
            bot=False,
            data={"grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri},
            auth=(self.app_id, self._secret),
        )

    async def me(self, access_token: str) -> dict:
        return await self._request("GET", "/users/@me", bot=False, headers={"Authorization": f"Bearer {access_token}"})
