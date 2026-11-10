"""What happened in a group's run, for the Discord bot (SPEC 19) and later live updates (SPEC 12.3).

The game rules call `emit` in the same transaction as the change they make, so an event exists
exactly when the change was saved. A background job (jobs/discord_bot.py) reads the outbox.
"""

from sqlmodel import Session

from app.models import ChallengeGame, EventOutbox, Run


def emit(session: Session, group_id: int, type_: str, **payload) -> None:
    session.add(EventOutbox(group_id=group_id, type=type_, payload=payload))


def emit_for_game(session: Session, game: ChallengeGame, type_: str, **payload) -> None:
    run = session.get(Run, game.run_id)
    emit(session, run.group_id, type_, game_id=game.id, run_id=run.id, **payload)
