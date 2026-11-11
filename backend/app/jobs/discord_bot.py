"""Background sender for the Discord bot (services/discord_bot.py, SPEC 19).

Every SEND_SECONDS it sends what the event outbox has waiting. Less often it edits live
scoreboards, posts reminders for games stuck without a result, posts each day's Daily Statline,
and early each month posts last month's Wrapped. On start it registers the slash commands (idempotent).

With the bot not set up, it only clears out old events now and then.
"""

import asyncio
import logging

from sqlalchemy.engine import Engine
from sqlmodel import Session, select

from app.config import get_settings
from app.models import Champion
from app.services import discord_bot, meta
from app.services.discord_api import DiscordClient

log = logging.getLogger("uvicorn.error")
SEND_SECONDS = 3
LIVE_EVERY = 5  # ticks: about every 15 seconds (each scoreboard is edited at most every 45)
SLOW_EVERY = 200  # ticks: about every 10 minutes
PRUNE_SECONDS = 3600


async def _static(engine: Engine) -> dict | None:
    with Session(engine) as session:
        version = session.exec(select(Champion.ddragon_version)).first()
    if not version:
        return None
    try:
        return await meta.load_static(version)
    except Exception:  # noqa: BLE001 - names and icons are optional
        return None


async def run_forever(engine: Engine, client_factory=DiscordClient) -> None:
    def new_session() -> Session:
        return Session(engine)

    if not get_settings().discord_enabled:
        while True:
            with new_session() as session:
                discord_bot.prune_outbox(session, keep_days=2)
                session.commit()
            await asyncio.sleep(PRUNE_SECONDS)

    client = client_factory()
    try:
        await client.set_commands(discord_bot.COMMANDS)
        log.info("Discord bot: %d slash commands registered", len(discord_bot.COMMANDS))
    except Exception as e:  # noqa: BLE001 - keep posting even if this fails
        log.warning("Discord bot: couldn't register slash commands: %s", e)

    tick = 0
    while True:
        try:
            await discord_bot.send_outbox(new_session, client)
            if tick % LIVE_EVERY == 0:
                await discord_bot.refresh_live(new_session, client, await _static(engine))
            if tick % SLOW_EVERY == 0:
                await discord_bot.post_nudges(new_session, client)
                await discord_bot.post_wrapped(new_session, client)
                await discord_bot.post_daily(new_session, client)
                with new_session() as session:
                    discord_bot.prune_outbox(session)
                    session.commit()
        except Exception:  # noqa: BLE001 - never let the loop die
            log.exception("Discord bot loop failed")
        tick += 1
        await asyncio.sleep(SEND_SECONDS)
