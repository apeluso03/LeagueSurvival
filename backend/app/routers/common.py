"""Shared lookups and response builders for routers."""

from fastapi import HTTPException
from sqlmodel import Session, func, select

from app.models import (
    AppSettings,
    ChallengeGame,
    Champion,
    PlayerMatchStats,
    PoolEntry,
    PoolEvent,
    ReviveToken,
    RiotMatch,
    Run,
)
from app.schemas import AssignmentOut, GameOut, MatchPlayerOut, MatchSummaryOut, RunOut
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


def match_summary(session: Session, game: ChallengeGame, assignments) -> MatchSummaryOut | None:
    match = session.get(RiotMatch, game.riot_match_id) if game.riot_match_id else None
    if match is None:
        return None
    options = {a.player_id: a.options for a in assignments}
    rows = session.exec(
        select(PlayerMatchStats).where(
            PlayerMatchStats.match_id == match.match_id, PlayerMatchStats.player_id.in_(list(options))
        )
    ).all()
    champ_by_key = {c.key: c.id for c in session.exec(select(Champion)).all()}
    players = []
    for r in rows:
        cid = champ_by_key.get(r.champion_key)
        players.append(
            MatchPlayerOut(
                player_id=r.player_id, champion_id=cid, team_id=r.team_id, win=r.win,
                kills=r.kills, deaths=r.deaths, assists=r.assists, in_options=cid in options[r.player_id],
            )
        )
    return MatchSummaryOut(
        match_id=match.match_id, queue_id=match.queue_id, game_start=match.game_start,
        game_duration=match.game_duration, early_surrender=match.early_surrender, players=players,
    )


def game_out(session: Session, game: ChallengeGame) -> GameOut:
    eliminated = session.exec(
        select(PoolEvent.champion_id).where(
            PoolEvent.game_id == game.id, PoolEvent.type == "eliminate", PoolEvent.undone == False  # noqa: E712
        )
    ).all()
    earned = session.exec(select(ReviveToken.player_id).where(ReviveToken.earned_in_game_id == game.id)).all()
    assignments = rules.assignments_for(session, game.id)
    return GameOut(
        **game.model_dump(),
        assignments=[AssignmentOut(**a.model_dump()) for a in assignments],
        eliminated=list(eliminated),
        tokens_earned=list(earned),
        match=match_summary(session, game, assignments),
    )
