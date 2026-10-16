"""Who is signed in, and what they may do.

- Site owner (`User.is_admin`, the first account): everything.
- Run owner (`Run.owner_user_id`): spins, results, undo, pool fixes and shop settings for that run,
  and every player's gold, shop and items in it (so one person can still run the whole group).
- Everyone else: sees the runs, pool, stats and history, and manages their own player's gold,
  shop, items and revive tokens.
"""

from fastapi import Depends, HTTPException, Request
from sqlmodel import Session

from app.db import get_session
from app.models import Run, User
from app.services import auth


def optional_user(request: Request, session: Session = Depends(get_session)) -> User | None:
    return auth.user_for_token(session, request.cookies.get(auth.SESSION_COOKIE))


def current_user(user: User | None = Depends(optional_user)) -> User:
    if user is None:
        raise HTTPException(401, "Sign in to continue")
    return user


def require_admin(user: User = Depends(current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(403, "Only the site owner can do that")
    return user


def can_manage(user: User, run: Run) -> bool:
    return user.is_admin or (run.owner_user_id is not None and run.owner_user_id == user.id)


def require_manager(user: User, run: Run) -> None:
    if not can_manage(user, run):
        raise HTTPException(403, "Only the run's owner can do that")


def can_act_for(user: User, run: Run, player_id: int) -> bool:
    return can_manage(user, run) or (user.player_id is not None and user.player_id == player_id)


def require_act_for(user: User, run: Run, player_id: int) -> None:
    if not can_act_for(user, run, player_id):
        raise HTTPException(403, "You can only do that for your own player")
