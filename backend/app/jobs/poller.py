"""Background match polling (SPEC 9.3).

Runs every `poll_interval_seconds`, but only does anything while challenge mode is on, a Riot key
is set, and a challenge game is pending. Each poll imports recent matches for the players in the
pending game(s), then runs the matcher.
"""

import asyncio
import logging

from sqlalchemy.engine import Engine
from sqlmodel import Session, col, select

from app.config import get_settings
from app.models import AppSettings, ChallengeGame, Run, SpinAssignment
from app.services import matcher, sync
from app.services.riot_client import RiotClient

log = logging.getLogger("uvicorn.error")
MIN_INTERVAL = 30


def pending_player_ids(session: Session) -> list[int]:
    active_runs = select(Run.id).where(Run.status == "active")
    pending = select(ChallengeGame.id).where(
        ChallengeGame.status == "pending",
        col(ChallengeGame.needs_review).is_(False),
        col(ChallengeGame.run_id).in_(active_runs),
    )
    return sorted(set(session.exec(select(SpinAssignment.player_id).where(col(SpinAssignment.game_id).in_(pending))).all()))


async def poll_once(engine: Engine, client_factory=RiotClient) -> list[matcher.Outcome] | None:
    """One poll. Returns the matcher outcomes, or None when there was nothing to do."""
    with Session(engine) as session:
        settings = session.get(AppSettings, 1)
        if settings is None or not settings.challenge_mode or not get_settings().riot_api_key:
            return None
        player_ids = pending_player_ids(session)
        if not player_ids:
            return None
        async with client_factory() as client:
            await sync.sync_all(session, client, player_ids)
        outcomes = matcher.run_matcher(session)
        session.commit()
        for o in outcomes:
            if o.status in ("applied", "voided", "needs_review"):
                log.info("Game %s: %s %s", o.game_id, o.status, o.message)
        return outcomes


async def run_forever(engine: Engine) -> None:
    while True:
        try:
            await poll_once(engine)
        except Exception:  # noqa: BLE001 - keep polling after unexpected errors
            log.exception("Match poll failed")
        with Session(engine) as session:
            settings = session.get(AppSettings, 1)
            interval = max(MIN_INTERVAL, settings.poll_interval_seconds if settings else 90)
        await asyncio.sleep(interval)
