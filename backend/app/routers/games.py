from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, col, select

from app.db import get_session
from app.models import ChallengeGame, Player, RiotMatch
from app.routers.common import champion_keys, game_out, get_app_settings, get_or_404
from app.schemas import AssignmentsPatch, GameOut, LinkMatchIn, ResultIn, ReviewIn
from app.services import matcher, rules, sync
from app.services.riot_client import RiotClient, RiotError

router = APIRouter(prefix="/api/games", tags=["games"])


@router.get("", response_model=list[GameOut])
def list_games(run_id: int | None = None, session: Session = Depends(get_session)):
    query = select(ChallengeGame).order_by(col(ChallengeGame.id).desc())
    if run_id is not None:
        query = query.where(ChallengeGame.run_id == run_id)
    keys = champion_keys(session)  # once for the whole list, not once per game
    return [game_out(session, g, keys) for g in session.exec(query).all()]


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


@router.post("/{game_id}/review", response_model=GameOut)
def review(game_id: int, body: ReviewIn, session: Session = Depends(get_session)):
    """For a game flagged "needs review": accept the Riot match anyway, or reject it."""
    game = get_or_404(session, ChallengeGame, game_id, "Game")
    if body.action == "accept":
        matcher.accept_review(session, game, get_app_settings(session))
    else:
        matcher.reject_review(session, game)
    session.commit()
    return game_out(session, game)


@router.post("/{game_id}/link-match", response_model=GameOut)
async def link_match(game_id: int, body: LinkMatchIn, session: Session = Depends(get_session)):
    """Attach a Riot match to a hand-recorded game and pay out its gold (SPEC 7.7). The recorded
    result stays as it is. Fetches the match from Riot if it hasn't been imported yet."""
    game = get_or_404(session, ChallengeGame, game_id, "Game")
    match_id = body.riot_match_id.strip().upper()
    if "_" not in match_id:
        raise HTTPException(400, "Match IDs look like NA1_1234567890")
    if session.get(RiotMatch, match_id) is None:
        first = rules.assignments_for(session, game.id)[0]
        region = session.get(Player, first.player_id).region
        try:
            async with RiotClient() as client:
                sync.store_match(session, await client.match(region, match_id))
        except RiotError as e:
            raise HTTPException(404 if e.status == 404 else 502, str(e)) from e
    matcher.link_match_by_id(session, game, match_id)
    session.commit()
    return game_out(session, game)
