"""Who is signed in, which group they're looking at, and what they may do there.

- Group owner (`GroupMember.role == "owner"`): everything in their group: players, runs, settings,
  invites and members.
- Run owner (`Run.owner_user_id`): spins, results, undo, pool fixes and shop settings for that run,
  and every player's gold, shop and items in it (so one person can still run the whole group).
- Members: see the group's runs, pool, stats and history, and manage their own player's gold, shop,
  items and revive tokens.
- Site admin (`User.is_admin`, the first account): site-wide things only (site invites, open
  sign-up, the build crawler, Riot data deletion). No extra powers inside other people's groups.

Everything in another group answers 404, so ids don't reveal which groups exist.
"""

from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request
from sqlmodel import Session

from app.db import get_session
from app.models import ChallengeGame, Group, GroupMember, Player, Run, User
from app.services import auth


@dataclass
class Ctx:
    user: User
    group: Group | None
    member: GroupMember | None

    @property
    def group_id(self) -> int:
        assert self.group is not None
        return self.group.id

    @property
    def is_owner(self) -> bool:
        return self.member is not None and self.member.role == "owner"

    @property
    def player_id(self) -> int | None:
        return self.member.player_id if self.member else None


def optional_user(request: Request, session: Session = Depends(get_session)) -> User | None:
    return auth.user_for_token(session, request.cookies.get(auth.SESSION_COOKIE))


def current_user(user: User | None = Depends(optional_user)) -> User:
    if user is None:
        raise HTTPException(401, "Sign in to continue")
    return user


def require_admin(user: User = Depends(current_user)) -> User:
    """The site admin (site-wide settings), not a group owner."""
    if not user.is_admin:
        raise HTTPException(403, "Only the site admin can do that")
    return user


def current_ctx(request: Request, user: User = Depends(current_user), session: Session = Depends(get_session)) -> Ctx:
    """The group this browser is viewing (falls back to the user's first group)."""
    row = auth.session_for_token(session, request.cookies.get(auth.SESSION_COOKIE))
    member = auth.membership(session, row.group_id, user.id) if row and row.group_id else None
    if member is None:
        member = next(iter(auth.memberships(session, user.id)), None)
        if row is not None and member is not None:
            row.group_id = member.group_id
            session.add(row)
            session.commit()
    group = session.get(Group, member.group_id) if member else None
    return Ctx(user=user, group=group, member=member)


def group_ctx(ctx: Ctx = Depends(current_ctx)) -> Ctx:
    if ctx.group is None:
        raise HTTPException(409, "Start a group or join one with an invite link first")
    return ctx


def require_owner(ctx: Ctx = Depends(group_ctx)) -> Ctx:
    if not ctx.is_owner:
        raise HTTPException(403, "Only the group's owner can do that")
    return ctx


# --- things that must belong to the current group -----------------------------------------------


def get_run(session: Session, ctx: Ctx, run_id: int) -> Run:
    run = session.get(Run, run_id)
    if run is None or run.group_id != ctx.group_id:
        raise HTTPException(404, f"Run {run_id} not found")
    return run


def get_player(session: Session, ctx: Ctx, player_id: int) -> Player:
    player = session.get(Player, player_id)
    if player is None or player.group_id != ctx.group_id:
        raise HTTPException(404, f"Player {player_id} not found")
    return player


def get_game(session: Session, ctx: Ctx, game_id: int) -> ChallengeGame:
    game = session.get(ChallengeGame, game_id)
    if game is None or session.get(Run, game.run_id).group_id != ctx.group_id:
        raise HTTPException(404, f"Game {game_id} not found")
    return game


# --- permissions ---------------------------------------------------------------------------------


def can_manage(ctx: Ctx, run: Run) -> bool:
    if ctx.group is None or run.group_id != ctx.group.id:
        return False
    return ctx.is_owner or (run.owner_user_id is not None and run.owner_user_id == ctx.user.id)


def require_manager(ctx: Ctx, run: Run) -> None:
    if not can_manage(ctx, run):
        raise HTTPException(403, "Only the run's owner can do that")


def can_act_for(ctx: Ctx, run: Run, player_id: int) -> bool:
    return can_manage(ctx, run) or (ctx.player_id is not None and ctx.player_id == player_id and run.group_id == ctx.group_id)


def require_act_for(ctx: Ctx, run: Run, player_id: int) -> None:
    if not can_act_for(ctx, run, player_id):
        raise HTTPException(403, "You can only do that for your own player")
