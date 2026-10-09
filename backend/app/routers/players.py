from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, col, delete, select

from app.config import get_settings
from app.db import get_session
from app.models import Player, PlayerMatchStats, ReviveToken, SpinAssignment
from app.routers.common import get_app_settings, get_or_404
from app.schemas import PlayerIn, PlayerOut, PlayerPatch
from app.services import sync
from app.services.riot_client import REGIONS, RiotClient, RiotError

router = APIRouter(prefix="/api/players", tags=["players"])


def _check_region(region: str | None) -> None:
    if region is not None and region not in REGIONS:
        raise HTTPException(400, f"Region must be one of {', '.join(REGIONS)}")


async def _try_link(session: Session, player: Player) -> str | None:
    """Look up the PUUID if a Riot ID and API key are present.

    A Riot ID that doesn't exist is an error the user should fix (404). Anything else (no key, key
    expired, Riot down) is returned as a message and the player is saved unlinked.
    """
    if not (player.riot_game_name and player.riot_tag_line) or not get_settings().riot_api_key:
        return None
    try:
        async with RiotClient() as client:
            await sync.link_player(session, client, player)
    except RiotError as e:
        if e.status == 404:
            raise HTTPException(
                404, f"Riot ID {player.riot_game_name}#{player.riot_tag_line} not found in {player.region}"
            ) from e
        return str(e)
    return None


def player_out(player: Player, link_error: str | None = None) -> PlayerOut:
    return PlayerOut(**player.model_dump(), link_error=link_error)


@router.get("", response_model=list[PlayerOut])
def list_players(session: Session = Depends(get_session)):
    return [player_out(p) for p in session.exec(select(Player).order_by(col(Player.display_name))).all()]


@router.post("", response_model=PlayerOut, status_code=201)
async def create_player(body: PlayerIn, session: Session = Depends(get_session)):
    _check_region(body.region)
    player = Player(**body.model_dump())
    link_error = await _try_link(session, player)
    session.add(player)
    session.commit()
    session.refresh(player)
    return player_out(player, link_error)


@router.patch("/{player_id}", response_model=PlayerOut)
async def update_player(player_id: int, body: PlayerPatch, session: Session = Depends(get_session)):
    player = get_or_404(session, Player, player_id, "Player")
    changes = body.model_dump(exclude_unset=True)
    _check_region(changes.get("region"))
    riot_changed = any(
        k in changes and changes[k] != getattr(player, k) for k in ("riot_game_name", "riot_tag_line", "region")
    )
    for field, value in changes.items():
        setattr(player, field, value)
    link_error = None
    if riot_changed:
        player.puuid = None  # Riot ID changed; needs a fresh lookup
        link_error = await _try_link(session, player)
    session.add(player)
    session.commit()
    session.refresh(player)
    return player_out(player, link_error)


@router.post("/{player_id}/link", response_model=PlayerOut)
async def link_player(player_id: int, session: Session = Depends(get_session)):
    """Retry the Riot ID lookup. Errors are returned as HTTP errors so the UI can show them."""
    player = get_or_404(session, Player, player_id, "Player")
    try:
        async with RiotClient() as client:
            await sync.link_player(session, client, player)
    except RiotError as e:
        # 404: unknown Riot ID; 0/400: nothing to look up or no key (user can fix); else Riot-side trouble
        code = e.status if e.status in (400, 404) else 400 if e.status == 0 else 502
        raise HTTPException(code, str(e)) from e
    session.commit()
    session.refresh(player)
    return player_out(player)


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
    session.exec(delete(PlayerMatchStats).where(col(PlayerMatchStats.player_id) == player_id))
    session.delete(player)
    session.commit()
