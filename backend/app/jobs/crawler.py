"""Background high-elo match crawler (services/meta.py).

Runs while the crawler is switched on in Settings and a Riot key is set. It waits PAUSE_SECONDS
between Riot calls (about half a personal key's limit), so the match poller always has room.
"""

import asyncio
import logging

from sqlalchemy.engine import Engine
from sqlmodel import Session

from app.config import get_settings
from app.models import SiteSettings
from app.services import meta
from app.services.riot_client import RiotClient, RiotError

log = logging.getLogger("uvicorn.error")
PAUSE_SECONDS = 2.5
IDLE_SECONDS = 60  # when switched off, or after an error


async def crawl_once(engine: Engine, client_factory=RiotClient, pause=None) -> int | None:
    """One crawler step. Returns matches counted, or None when it's switched off."""
    with Session(engine) as session:
        settings = session.get(SiteSettings, 1)
        if settings is None or not settings.meta_crawl or not get_settings().riot_api_key:
            return None
        async with client_factory() as client:
            try:
                return await meta.crawl_step(session, client, pause=pause)  # commits as it goes
            except RiotError as e:
                session.rollback()
                state = meta.crawl_state(session)
                state.last_error = str(e)
                session.add(state)
                session.commit()
                raise


async def run_forever(engine: Engine) -> None:
    async def pause():
        await asyncio.sleep(PAUSE_SECONDS)

    while True:
        try:
            counted = await crawl_once(engine, pause=pause)
            await asyncio.sleep(PAUSE_SECONDS if counted is not None else IDLE_SECONDS)
        except Exception as e:  # noqa: BLE001 - keep crawling after unexpected errors
            log.warning("Meta crawler: %s", e)
            await asyncio.sleep(IDLE_SECONDS)
