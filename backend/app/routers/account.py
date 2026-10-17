"""Sign up, sign in and out, invite links and account management."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlmodel import Session, col, select

from app.db import get_session
from app.models import Invite, Player, User
from app.routers.access import current_user, optional_user, require_admin
from app.services import auth

router = APIRouter(prefix="/api", tags=["account"])


class MeUser(BaseModel):
    id: int
    username: str
    player_id: int | None
    is_admin: bool


class MeOut(BaseModel):
    user: MeUser | None
    # No accounts exist yet: the first person to sign up becomes the site owner.
    setup_needed: bool = False
    # Only while setting up, so the owner can say which player they are.
    players: list[dict] = []


class Credentials(BaseModel):
    username: str = Field(max_length=100)
    password: str = Field(max_length=auth.MAX_PASSWORD)


class SetupIn(Credentials):
    player_id: int | None = None


class RegisterIn(Credentials):
    token: str = Field(max_length=200)


class PasswordIn(BaseModel):
    current_password: str = Field(max_length=auth.MAX_PASSWORD)
    new_password: str = Field(max_length=auth.MAX_PASSWORD)


class InviteInfoOut(BaseModel):
    player_id: int
    display_name: str
    expires_at: datetime


class AccountOut(BaseModel):
    id: int
    username: str
    player_id: int | None
    is_admin: bool
    created_at: datetime
    last_login_at: datetime | None


class InviteOut(BaseModel):
    id: int
    player_id: int
    created_at: datetime
    expires_at: datetime


class NewInviteOut(InviteOut):
    token: str  # shown once; the link is /invite/<token>


class InviteIn(BaseModel):
    player_id: int


class AccountsOut(BaseModel):
    accounts: list[AccountOut]
    invites: list[InviteOut]


def me_out(session: Session, user: User | None) -> MeOut:
    if user is not None:
        # Attribute access (not model_dump) so a row expired by a commit is reloaded first.
        return MeOut(user=MeUser(id=user.id, username=user.username, player_id=user.player_id, is_admin=user.is_admin))
    if auth.user_count(session) == 0:
        players = session.exec(select(Player).order_by(col(Player.display_name))).all()
        return MeOut(user=None, setup_needed=True, players=[{"id": p.id, "display_name": p.display_name} for p in players])
    return MeOut(user=None)


def _sign_in(request: Request, response: Response, session: Session, user: User) -> None:
    token = auth.start_session(session, user)
    session.commit()
    response.set_cookie(
        auth.SESSION_COOKIE,
        token,
        max_age=auth.SESSION_DAYS * 24 * 3600,
        httponly=True,  # page scripts can't read it
        samesite="lax",  # other sites can't send requests with it
        secure=request.url.scheme == "https",
        path="/",
    )


@router.get("/auth/me", response_model=MeOut)
def me(user: User | None = Depends(optional_user), session: Session = Depends(get_session)):
    return me_out(session, user)


@router.post("/auth/setup", response_model=MeOut)
def set_up(body: SetupIn, request: Request, response: Response, session: Session = Depends(get_session)):
    """Make the first account (the site owner). Only works while there are no accounts."""
    user = auth.set_up_owner(session, body.username, body.password, body.player_id)
    _sign_in(request, response, session, user)
    return me_out(session, user)


@router.post("/auth/login", response_model=MeOut)
def login(body: Credentials, request: Request, response: Response, session: Session = Depends(get_session)):
    address = request.client.host if request.client else "?"
    pair = f"{address}|{body.username.strip().lower()}"
    wait = max(auth.pair_throttle.wait_seconds(pair), auth.address_throttle.wait_seconds(address))
    if wait:
        minutes = (wait + 59) // 60
        raise HTTPException(429, f"Too many wrong passwords. Try again in {minutes} minute{'s' if minutes != 1 else ''}.")
    user = auth.authenticate(session, body.username, body.password)
    if user is None:
        auth.pair_throttle.miss(pair)
        auth.address_throttle.miss(address)
        raise HTTPException(401, "Wrong username or password")
    auth.pair_throttle.clear(pair)
    _sign_in(request, response, session, user)
    return me_out(session, user)


@router.post("/auth/logout", status_code=204)
def logout(request: Request, response: Response, session: Session = Depends(get_session)):
    auth.end_session(session, request.cookies.get(auth.SESSION_COOKIE))
    session.commit()
    response.delete_cookie(auth.SESSION_COOKIE, path="/")


@router.post("/auth/password", response_model=MeOut)
def change_password(
    body: PasswordIn,
    request: Request,
    response: Response,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
):
    """Change your password. Signs out your other browsers; this one stays signed in."""
    auth.change_password(session, user, body.current_password, body.new_password)
    _sign_in(request, response, session, user)
    return me_out(session, user)


@router.get("/auth/invites/{token}", response_model=InviteInfoOut)
def invite_info(token: str, session: Session = Depends(get_session)):
    """What an invite link is for, so the sign-up page can say "You're joining as Bea"."""
    invite = auth.invite_for_token(session, token)
    player = session.get(Player, invite.player_id)
    return InviteInfoOut(player_id=player.id, display_name=player.display_name, expires_at=invite.expires_at)


@router.post("/auth/register", response_model=MeOut)
def register(body: RegisterIn, request: Request, response: Response, session: Session = Depends(get_session)):
    """Make an account from an invite link. It plays as the invited player."""
    user = auth.accept_invite(session, body.token, body.username, body.password)
    _sign_in(request, response, session, user)
    return me_out(session, user)


# --- site owner: accounts and invites ---


@router.get("/accounts", response_model=AccountsOut)
def list_accounts(_: User = Depends(require_admin), session: Session = Depends(get_session)):
    accounts = session.exec(select(User).order_by(col(User.username))).all()
    return AccountsOut(
        accounts=[AccountOut(**u.model_dump()) for u in accounts],
        invites=[InviteOut(**i.model_dump()) for i in auth.open_invites(session)],
    )


@router.post("/accounts/invites", response_model=NewInviteOut, status_code=201)
def create_invite(body: InviteIn, user: User = Depends(require_admin), session: Session = Depends(get_session)):
    invite, token = auth.create_invite(session, body.player_id, user)
    session.commit()
    session.refresh(invite)
    return NewInviteOut(**invite.model_dump(), token=token)


@router.delete("/accounts/invites/{invite_id}", status_code=204)
def revoke_invite(invite_id: int, _: User = Depends(require_admin), session: Session = Depends(get_session)):
    invite = session.get(Invite, invite_id)
    if invite is None:
        raise HTTPException(404, "Invite not found")
    invite.revoked = True
    session.add(invite)
    session.commit()


@router.delete("/accounts/{user_id}", status_code=204)
def delete_account(user_id: int, me_: User = Depends(require_admin), session: Session = Depends(get_session)):
    """Remove someone's account (lost password, wrong person). Their player and history stay."""
    if user_id == me_.id:
        raise HTTPException(400, "You can't remove your own account")
    target = session.get(User, user_id)
    if target is None:
        raise HTTPException(404, "Account not found")
    auth.delete_user(session, target)
    session.commit()
