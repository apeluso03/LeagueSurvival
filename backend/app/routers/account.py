"""Sign up, sign in and out, groups, invite links, members and site settings."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlmodel import Session, col, func, select

from app.db import get_session
from app.models import Group, GroupMember, Invite, Player, SiteInvite, User
from app.routers.access import Ctx, current_user, optional_user, require_admin, require_owner
from app.services import auth

router = APIRouter(prefix="/api", tags=["account"])


# --- shapes ------------------------------------------------------------------------------------


class MeUser(BaseModel):
    id: int
    username: str
    is_admin: bool  # site admin


class MeGroup(BaseModel):
    id: int
    name: str
    role: str  # "owner" | "member"
    player_id: int | None


class MeOut(BaseModel):
    user: MeUser | None
    groups: list[MeGroup] = []
    group: MeGroup | None = None  # the one this browser is viewing
    # No accounts exist yet: the first person to sign up becomes the site admin.
    setup_needed: bool = False
    # Only while setting up, so the admin can say which player they are.
    players: list[dict] = []
    open_signup: bool = False


class Credentials(BaseModel):
    username: str = Field(max_length=100)
    password: str = Field(max_length=auth.MAX_PASSWORD)


class SetupIn(Credentials):
    player_id: int | None = None


class RegisterIn(Credentials):
    token: str = Field(max_length=200)


class SignupIn(Credentials):
    group_name: str = Field(max_length=60)
    code: str | None = Field(default=None, max_length=200)  # a site invite code


class GroupIn(BaseModel):
    name: str = Field(max_length=60)
    code: str | None = Field(default=None, max_length=200)


class GroupPatch(BaseModel):
    name: str = Field(max_length=60)


class PasswordIn(BaseModel):
    current_password: str = Field(max_length=auth.MAX_PASSWORD)
    new_password: str = Field(max_length=auth.MAX_PASSWORD)


class InviteInfoOut(BaseModel):
    player_id: int
    display_name: str
    group_name: str
    expires_at: datetime


class AccountOut(BaseModel):
    id: int
    username: str
    role: str
    player_id: int | None
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


class SiteInviteOut(BaseModel):
    id: int
    note: str
    created_at: datetime
    expires_at: datetime


class NewSiteInviteOut(SiteInviteOut):
    code: str  # shown once


class SiteInviteIn(BaseModel):
    note: str = Field(default="", max_length=80)


class SiteOut(BaseModel):
    open_signup: bool
    groups: int
    users: int
    invites: list[SiteInviteOut]


class SitePatch(BaseModel):
    open_signup: bool


# --- helpers -----------------------------------------------------------------------------------


def _group_out(session: Session, m: GroupMember) -> MeGroup:
    g = session.get(Group, m.group_id)
    return MeGroup(id=g.id, name=g.name, role=m.role, player_id=m.player_id)


def me_out(session: Session, user: User | None, group_id: int | None = None) -> MeOut:
    open_signup = auth.site_settings(session).open_signup
    if user is not None:
        mine = auth.memberships(session, user.id)
        groups = [_group_out(session, m) for m in mine]
        current = next((g for g in groups if g.id == group_id), groups[0] if groups else None)
        return MeOut(
            user=MeUser(id=user.id, username=user.username, is_admin=user.is_admin),
            groups=groups,
            group=current,
            open_signup=open_signup,
        )
    if auth.user_count(session) == 0:
        players = session.exec(select(Player).order_by(col(Player.display_name))).all()
        return MeOut(user=None, setup_needed=True, players=[{"id": p.id, "display_name": p.display_name} for p in players])
    return MeOut(user=None, open_signup=open_signup)


def _sign_in(request: Request, response: Response, session: Session, user: User, group_id: int | None = None) -> str:
    token = auth.start_session(session, user)
    if group_id is not None:
        auth.switch_group(session, token, user, group_id)
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
    return token


def _current_group_id(request: Request, session: Session) -> int | None:
    row = auth.session_for_token(session, request.cookies.get(auth.SESSION_COOKIE))
    return row.group_id if row else None


# --- signing in --------------------------------------------------------------------------------


@router.get("/auth/me", response_model=MeOut)
def me(request: Request, user: User | None = Depends(optional_user), session: Session = Depends(get_session)):
    return me_out(session, user, _current_group_id(request, session) if user else None)


@router.post("/auth/setup", response_model=MeOut)
def set_up(body: SetupIn, request: Request, response: Response, session: Session = Depends(get_session)):
    """Make the first account (the site admin). Only works while there are no accounts."""
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
    group_id = _current_group_id(request, session)
    auth.change_password(session, user, body.current_password, body.new_password)
    _sign_in(request, response, session, user, group_id)
    return me_out(session, user, group_id)


# --- starting and joining groups -----------------------------------------------------------------

@router.post("/auth/signup", response_model=MeOut)
def sign_up(body: SignupIn, request: Request, response: Response, session: Session = Depends(get_session)):
    """A new account that starts its own group (with a site invite code, or while sign-up is open)."""
    address = request.client.host if request.client else "?"
    if auth.signup_throttle.wait_seconds(address):
        raise HTTPException(429, "Too many new accounts from here. Try again later.")
    user = auth.sign_up(session, body.username, body.password, body.group_name, body.code)
    auth.signup_throttle.miss(address)
    _sign_in(request, response, session, user)
    return me_out(session, user)


@router.get("/auth/invites/{token}", response_model=InviteInfoOut)
def invite_info(token: str, session: Session = Depends(get_session)):
    """What an invite link is for, so the page can say "Join Alex's group as Bea"."""
    invite = auth.invite_for_token(session, token)
    player = session.get(Player, invite.player_id)
    group = session.get(Group, invite.group_id)
    return InviteInfoOut(player_id=player.id, display_name=player.display_name, group_name=group.name, expires_at=invite.expires_at)


@router.post("/auth/register", response_model=MeOut)
def register(body: RegisterIn, request: Request, response: Response, session: Session = Depends(get_session)):
    """Make an account from an invite link. It plays as the invited player in that group."""
    invite = auth.invite_for_token(session, body.token)
    user = auth.accept_invite(session, body.token, body.username, body.password)
    _sign_in(request, response, session, user, invite.group_id)
    return me_out(session, user, invite.group_id)


@router.post("/auth/invites/{token}/accept", response_model=MeOut)
def accept_invite(token: str, request: Request, user: User = Depends(current_user), session: Session = Depends(get_session)):
    """Join another group with the account you're signed in with."""
    m = auth.accept_invite_signed_in(session, token, user)
    auth.switch_group(session, request.cookies.get(auth.SESSION_COOKIE), user, m.group_id)
    session.commit()
    return me_out(session, user, m.group_id)


@router.post("/groups", response_model=MeOut, status_code=201)
def start_group(body: GroupIn, request: Request, user: User = Depends(current_user), session: Session = Depends(get_session)):
    """Start another group with the account you're signed in with."""
    group = auth.start_group(session, user, body.name, body.code)
    auth.switch_group(session, request.cookies.get(auth.SESSION_COOKIE), user, group.id)
    session.commit()
    return me_out(session, user, group.id)


@router.post("/groups/{group_id}/switch", response_model=MeOut)
def switch_group(group_id: int, request: Request, user: User = Depends(current_user), session: Session = Depends(get_session)):
    auth.switch_group(session, request.cookies.get(auth.SESSION_COOKIE), user, group_id)
    session.commit()
    return me_out(session, user, group_id)


@router.patch("/groups/current", response_model=MeOut)
def rename_group(body: GroupPatch, ctx: Ctx = Depends(require_owner), session: Session = Depends(get_session)):
    ctx.group.name = auth.clean_group_name(body.name)
    session.add(ctx.group)
    session.commit()
    return me_out(session, ctx.user, ctx.group_id)


# --- group owner: members and invites ----------------------------------------------------------------


@router.get("/accounts", response_model=AccountsOut)
def list_accounts(ctx: Ctx = Depends(require_owner), session: Session = Depends(get_session)):
    rows = session.exec(
        select(GroupMember, User).join(User, col(User.id) == col(GroupMember.user_id)).where(GroupMember.group_id == ctx.group_id)
    ).all()
    return AccountsOut(
        accounts=[
            AccountOut(
                id=u.id, username=u.username, role=m.role, player_id=m.player_id,
                created_at=u.created_at, last_login_at=u.last_login_at,
            )
            for m, u in sorted(rows, key=lambda r: r[1].username)
        ],
        invites=[InviteOut(**i.model_dump()) for i in auth.open_invites(session, ctx.group_id)],
    )


@router.post("/accounts/invites", response_model=NewInviteOut, status_code=201)
def create_invite(body: InviteIn, ctx: Ctx = Depends(require_owner), session: Session = Depends(get_session)):
    invite, token = auth.create_invite(session, ctx.group, body.player_id, ctx.user)
    session.commit()
    session.refresh(invite)
    return NewInviteOut(**invite.model_dump(), token=token)


@router.delete("/accounts/invites/{invite_id}", status_code=204)
def revoke_invite(invite_id: int, ctx: Ctx = Depends(require_owner), session: Session = Depends(get_session)):
    invite = session.get(Invite, invite_id)
    if invite is None or invite.group_id != ctx.group_id:
        raise HTTPException(404, "Invite not found")
    invite.revoked = True
    session.add(invite)
    session.commit()


@router.delete("/accounts/{user_id}", status_code=204)
def remove_member(user_id: int, ctx: Ctx = Depends(require_owner), session: Session = Depends(get_session)):
    """Take someone out of the group (lost password, wrong person). Their player and history stay."""
    if user_id == ctx.user.id:
        raise HTTPException(400, "You can't remove yourself")
    target = session.get(User, user_id)
    if target is None or auth.membership(session, ctx.group_id, user_id) is None:
        raise HTTPException(404, "Account not found")
    auth.remove_member(session, ctx.group, target)
    session.commit()


# --- site admin ---------------------------------------------------------------------------------------


def _site_out(session: Session) -> SiteOut:
    return SiteOut(
        open_signup=auth.site_settings(session).open_signup,
        groups=session.exec(select(func.count()).select_from(Group)).one(),
        users=auth.user_count(session),
        invites=[SiteInviteOut(**i.model_dump()) for i in auth.open_site_invites(session)],
    )


@router.get("/site", response_model=SiteOut)
def read_site(_: User = Depends(require_admin), session: Session = Depends(get_session)):
    return _site_out(session)


@router.patch("/site", response_model=SiteOut)
def update_site(body: SitePatch, _: User = Depends(require_admin), session: Session = Depends(get_session)):
    site = auth.site_settings(session)
    site.open_signup = body.open_signup
    session.add(site)
    session.commit()
    return _site_out(session)


@router.post("/site/invites", response_model=NewSiteInviteOut, status_code=201)
def create_site_invite(body: SiteInviteIn, user: User = Depends(require_admin), session: Session = Depends(get_session)):
    """A one-time code someone uses to start their own group."""
    inv, code = auth.create_site_invite(session, user, body.note)
    session.commit()
    session.refresh(inv)
    return NewSiteInviteOut(**inv.model_dump(), code=code)


@router.delete("/site/invites/{invite_id}", status_code=204)
def revoke_site_invite(invite_id: int, _: User = Depends(require_admin), session: Session = Depends(get_session)):
    inv = session.get(SiteInvite, invite_id)
    if inv is None:
        raise HTTPException(404, "Invite not found")
    inv.revoked = True
    session.add(inv)
    session.commit()


