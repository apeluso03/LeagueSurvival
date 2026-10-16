"""Live game tracker (services/live.py).

While a challenge game is pending it:
- reads the game client on this PC every TICK_SECONDS (cheap: nothing answers when no game runs),
- asks Riot's Spectator API whether the players are in a game, every SEARCH_SECONDS until one is
  found, then every WATCH_SECONDS until it ends.
Both fill in everyone's champion as soon as the game loads.
"""

import asyncio
import logging
from datetime import timedelta

from sqlalchemy.engine import Engine
from sqlmodel import Session, select

from app.config import get_settings
from app.models import Champion, LiveGame, utcnow
from app.services import live, meta
from app.services.riot_client import RiotClient, RiotError

log = logging.getLogger("uvicorn.error")
TICK_SECONDS = 3
IDLE_SECONDS = 10  # no pending game
SEARCH_SECONDS = 30
WATCH_SECONDS = 60

# When each game was last searched for on Spectator before anything was found (no row to note it on).
_searched: dict[int, object] = {}


async def _static(session: Session) -> dict | None:
    version = session.exec(select(Champion.ddragon_version)).first()
    session.commit()  # never hold the database while waiting on the network
    if not version:
        return None
    try:
        return await meta.load_static(version)
    except Exception:  # noqa: BLE001 - names and icons are optional
        return None


def _spectator_due(game_id: int, row: LiveGame | None) -> bool:
    if row is not None and row.ended_at is not None:
        return False
    last = row.checked_at if row is not None and row.checked_at else _searched.get(game_id)
    if last is None:
        return True
    wait = WATCH_SECONDS if row is not None and row.riot_game_id else SEARCH_SECONDS
    return utcnow() - last >= timedelta(seconds=wait)


async def tick(engine: Engine, client_factory=RiotClient, fetch=live.fetch_live_client) -> int | None:
    """One pass. Returns the pending game's id, or None when there's nothing to track."""
    with Session(engine) as session:
        game = live.pending_game(session)
        if game is None:
            return None
        game_id = game.id
        static = await _static(session)

    data = await fetch()
    if data:
        with Session(engine) as session:
            game = session.get(live.ChallengeGame, game_id)
            if game is not None and game.status == "pending" and live.apply_client(session, game, data, static):
                session.commit()

    if get_settings().riot_api_key:
        with Session(engine) as session:
            game = session.get(live.ChallengeGame, game_id)
            if game is not None and game.status == "pending" and _spectator_due(game_id, session.get(LiveGame, game_id)):
                _searched[game_id] = utcnow()
                async with client_factory() as client:
                    try:
                        await live.check_spectator(session, client, game)
                    except RiotError as e:
                        session.rollback()
                        log.warning("Live game check: %s", e)
                        # Don't retry right away (a 403 or 429 would just repeat).
                        row = session.get(LiveGame, game_id)
                        if row is not None:
                            row.checked_at = utcnow()
                            session.add(row)
                            session.commit()
    return game_id


async def run_forever(engine: Engine) -> None:
    while True:
        try:
            game_id = await tick(engine)
        except Exception:  # noqa: BLE001 - keep tracking after unexpected errors
            log.exception("Live tracker failed")
            game_id = None
        await asyncio.sleep(TICK_SECONDS if game_id is not None else IDLE_SECONDS)
