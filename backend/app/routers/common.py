"""Shared lookups and response builders for routers."""

from fastapi import HTTPException
from sqlmodel import Session, func, select

from app.models import AppSettings, ChallengeGame, PoolEntry, PoolEvent, ReviveToken, Run
from app.schemas import AssignmentOut, GameOut, RunOut
from app.services import rules


def get_app_settings(session: Session) -> AppSettings:
    settings = session.get(AppSettings, 1)
    if settings is None:
        settings = AppSettings(id=1)
        session.add(settings)
        session.commit()
        session.refresh(settings)
    return settings


def get_or_404(session: Session, model, key, label: str):
    obj = session.get(model, key)
    if obj is None:
        raise HTTPException(404, f"{label} {key} not found")
    return obj


def run_out(session: Session, run: Run) -> RunOut:
    def count(*where) -> int:
        return session.exec(select(func.count()).select_from(PoolEntry).where(PoolEntry.run_id == run.id, *where)).one()

    pending = rules.pending_game(session, run.id)
    games_played = session.exec(
        select(func.count())
        .select_from(ChallengeGame)
        .where(ChallengeGame.run_id == run.id, ChallengeGame.status.in_(["won", "lost"]))
    ).one()
    return RunOut(
        **run.model_dump(),
        alive_count=count(PoolEntry.status == "alive"),
        total_count=count(),
        tokens_available=len(rules.available_tokens(session, run.id)),
        pending_game_id=pending.id if pending else None,
        games_played=games_played,
    )


def game_out(session: Session, game: ChallengeGame) -> GameOut:
    eliminated = session.exec(
        select(PoolEvent.champion_id).where(
            PoolEvent.game_id == game.id, PoolEvent.type == "eliminate", PoolEvent.undone == False  # noqa: E712
        )
    ).all()
    earned = session.exec(select(ReviveToken.player_id).where(ReviveToken.earned_in_game_id == game.id)).all()
    return GameOut(
        **game.model_dump(),
        assignments=[AssignmentOut(**a.model_dump()) for a in rules.assignments_for(session, game.id)],
        eliminated=list(eliminated),
        tokens_earned=list(earned),
    )
