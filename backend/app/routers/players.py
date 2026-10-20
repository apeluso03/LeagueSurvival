from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, col, delete, select

from app.config import get_settings
from app.db import get_session
from app.models import GroupMember, Player, PlayerMatchStats, ReviveToken, SpinAssignment, User
from app.routers.access import Ctx, can_act_for, get_player, get_run, group_ctx, require_owner
from app.routers.common import get_app_settings
from app.schemas import PlayerIn, PlayerOut, PlayerPatch
from app.services import achievements, recap, sync
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


# What a player may change about themselves; everything else (name, Riot ID) is the group owner's.
SELF_FIELDS = {"color", "title"}


def _usernames(session: Session, group_id: int) -> dict[int, str]:
    """player id -> the username of the account that plays as them, in this group."""
    rows = session.exec(
        select(GroupMember.player_id, User.username)
        .join(User, col(User.id) == col(GroupMember.user_id))
        .where(GroupMember.group_id == group_id, col(GroupMember.player_id).is_not(None))
    ).all()
    return {pid: name for pid, name in rows}


def player_out(session: Session, player: Player, link_error: str | None = None) -> PlayerOut:
    return PlayerOut(**player.model_dump(), link_error=link_error, username=_usernames(session, player.group_id).get(player.id))


@router.get("", response_model=list[PlayerOut])
def list_players(ctx: Ctx = Depends(group_ctx), session: Session = Depends(get_session)):
    usernames = _usernames(session, ctx.group_id)
    players = session.exec(select(Player).where(Player.group_id == ctx.group_id).order_by(col(Player.display_name))).all()
    return [PlayerOut(**p.model_dump(), username=usernames.get(p.id)) for p in players]


@router.post("", response_model=PlayerOut, status_code=201)
async def create_player(body: PlayerIn, ctx: Ctx = Depends(require_owner), session: Session = Depends(get_session)):
    _check_region(body.region)
    player = Player(**body.model_dump(), group_id=ctx.group_id)
    link_error = await _try_link(session, player)
    session.add(player)
    session.commit()
    session.refresh(player)
    return player_out(session, player, link_error)


@router.patch("/{player_id}", response_model=PlayerOut)
async def update_player(
    player_id: int, body: PlayerPatch, ctx: Ctx = Depends(group_ctx), session: Session = Depends(get_session)
):
    player = get_player(session, ctx, player_id)
    changes = body.model_dump(exclude_unset=True)
    if not ctx.is_owner:
        if ctx.player_id != player_id:
            raise HTTPException(403, "You can only edit your own player")
        if set(changes) - SELF_FIELDS:
            raise HTTPException(403, "Only the group's owner can change names and Riot IDs")
    _check_region(changes.get("region"))
    if changes.get("title") is not None:
        earned = achievements.evaluate(session).get(player_id, {})
        if changes["title"] not in earned:
            raise HTTPException(400, "That title comes from an achievement this player hasn't unlocked yet")
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
    return player_out(session, player, link_error)


@router.post("/{player_id}/link", response_model=PlayerOut)
async def link_player(player_id: int, ctx: Ctx = Depends(require_owner), session: Session = Depends(get_session)):
    """Retry the Riot ID lookup. Errors are returned as HTTP errors so the UI can show them."""
    player = get_player(session, ctx, player_id)
    try:
        async with RiotClient() as client:
            await sync.link_player(session, client, player)
    except RiotError as e:
        # 404: unknown Riot ID; 0/400: nothing to look up or no key (user can fix); else Riot-side trouble
        code = e.status if e.status in (400, 404) else 400 if e.status == 0 else 502
        raise HTTPException(code, str(e)) from e
    session.commit()
    session.refresh(player)
    return player_out(session, player)


@router.delete("/{player_id}", status_code=204)
def delete_player(player_id: int, ctx: Ctx = Depends(require_owner), session: Session = Depends(get_session)):
    player = get_player(session, ctx, player_id)
    if session.exec(select(GroupMember.user_id).where(GroupMember.player_id == player_id)).first():
        raise HTTPException(409, "Someone plays as this player. Remove their account first.")
    in_games = session.exec(select(SpinAssignment.id).where(SpinAssignment.player_id == player_id)).first()
    has_tokens = session.exec(select(ReviveToken.id).where(ReviveToken.player_id == player_id)).first()
    if in_games or has_tokens:
        raise HTTPException(409, "This player has challenge history and can't be deleted")
    s = get_app_settings(session, ctx.group_id)
    if player_id in s.last_used_player_ids:
        s.last_used_player_ids = [p for p in s.last_used_player_ids if p != player_id]
        session.add(s)
    session.exec(delete(PlayerMatchStats).where(col(PlayerMatchStats.player_id) == player_id))
    session.delete(player)
    session.commit()


@router.get("/{player_id}/profile")
def player_profile(
    player_id: int, run_id: int | None = None, ctx: Ctx = Depends(group_ctx), session: Session = Depends(get_session)
):
    """A player's page: stats, champions, recent games, runs, items and (for one run) gold over time.
    Items and the gold timeline are private: only the player and the group or run owner see them."""
    player = get_player(session, ctx, player_id)
    run = get_run(session, ctx, run_id) if run_id is not None else None
    profile = recap.player_profile(session, player, run_id)
    mine = ctx.is_owner or ctx.player_id == player_id or (run is not None and can_act_for(ctx, run, player_id))
    if not mine:
        profile["items"] = None
        profile["gold_timeline"] = None
        if isinstance(profile.get("stats"), dict):
            profile["stats"]["gold_balance"] = None
    return profile
