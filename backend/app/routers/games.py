from fastapi import APIRouter, Depends
from sqlmodel import Session, col, select

from app.db import get_session
from app.models import ChallengeGame
from app.routers.common import game_out, get_or_404
from app.schemas import AssignmentsPatch, GameOut, ResultIn
from app.services import rules

router = APIRouter(prefix="/api/games", tags=["games"])


@router.get("", response_model=list[GameOut])
def list_games(run_id: int | None = None, session: Session = Depends(get_session)):
    query = select(ChallengeGame).order_by(col(ChallengeGame.id).desc())
    if run_id is not None:
        query = query.where(ChallengeGame.run_id == run_id)
    return [game_out(session, g) for g in session.exec(query).all()]


@router.get("/{game_id}", response_model=GameOut)
def get_game(game_id: int, session: Session = Depends(get_session)):
    return game_out(session, get_or_404(session, ChallengeGame, game_id, "Game"))


@router.patch("/{game_id}/assignments", response_model=GameOut)
def set_assignments(game_id: int, body: AssignmentsPatch, session: Session = Depends(get_session)):
    game = get_or_404(session, ChallengeGame, game_id, "Game")
    rules.set_played(session, game, [rules.Pick(**p.model_dump()) for p in body.picks])
    session.commit()
    return game_out(session, game)


@router.post("/{game_id}/result", response_model=GameOut)
def set_result(game_id: int, body: ResultIn, session: Session = Depends(get_session)):
    game = get_or_404(session, ChallengeGame, game_id, "Game")
    rules.apply_result(session, game, body.result, source="manual", void_reason=body.reason)
    session.commit()
    return game_out(session, game)


@router.post("/{game_id}/undo", response_model=GameOut)
def undo(game_id: int, session: Session = Depends(get_session)):
    game = get_or_404(session, ChallengeGame, game_id, "Game")
    rules.undo_result(session, game)
    session.commit()
    return game_out(session, game)
