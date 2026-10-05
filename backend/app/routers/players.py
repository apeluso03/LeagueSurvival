from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, col, select

from app.db import get_session
from app.models import Player, ReviveToken, SpinAssignment
from app.routers.common import get_app_settings, get_or_404
from app.schemas import PlayerIn, PlayerPatch

router = APIRouter(prefix="/api/players", tags=["players"])


@router.get("", response_model=list[Player])
def list_players(session: Session = Depends(get_session)):
    return session.exec(select(Player).order_by(col(Player.display_name))).all()


@router.post("", response_model=Player, status_code=201)
def create_player(body: PlayerIn, session: Session = Depends(get_session)):
    # TODO(M3): resolve PUUID from Riot ID via Account-V1.
    player = Player(**body.model_dump())
    session.add(player)
    session.commit()
    session.refresh(player)
    return player


@router.patch("/{player_id}", response_model=Player)
def update_player(player_id: int, body: PlayerPatch, session: Session = Depends(get_session)):
    player = get_or_404(session, Player, player_id, "Player")
    changes = body.model_dump(exclude_unset=True)
    if {"riot_game_name", "riot_tag_line"} & changes.keys():
        player.puuid = None  # Riot ID changed; needs a fresh lookup
    for field, value in changes.items():
        setattr(player, field, value)
    session.add(player)
    session.commit()
    session.refresh(player)
    return player


@router.delete("/{player_id}", status_code=204)
def delete_player(player_id: int, session: Session = Depends(get_session)):
    player = get_or_404(session, Player, player_id, "Player")
    in_games = session.exec(select(SpinAssignment.id).where(SpinAssignment.player_id == player_id)).first()
    has_tokens = session.exec(select(ReviveToken.id).where(ReviveToken.player_id == player_id)).first()
    if in_games or has_tokens:
        raise HTTPException(409, "This player has challenge history and can't be deleted")
    s = get_app_settings(session)
    if player_id in s.last_used_player_ids:
        s.last_used_player_ids = [p for p in s.last_used_player_ids if p != player_id]
        session.add(s)
    session.delete(player)
    session.commit()
