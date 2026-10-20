"""Accounts, sign-in sessions and invite links.

Passwords are hashed with scrypt (Python's standard library, so there's nothing extra to install).
Session and invite tokens are random; the database only keeps their SHA-256, so a copy of the
database can't be used to sign in or to claim an invite.
"""

import base64
import hashlib
import hmac
import re
import secrets
import time
from collections import defaultdict, deque
from datetime import UTC, datetime, timedelta

from sqlmodel import Session, col, delete, func, select

from app.models import (
    AppSettings,
    AuthSession,
    Group,
    GroupMember,
    Invite,
    Player,
    Run,
    SiteInvite,
    SiteSettings,
    User,
    utcnow,
)
from app.services.rules import RuleError

SESSION_COOKIE = "lst_session"
SESSION_DAYS = 30
INVITE_DAYS = 7
SITE_INVITE_DAYS = 30

USERNAME_RE = re.compile(r"^[a-z0-9_.-]{3,24}$")
MIN_PASSWORD = 8
MAX_PASSWORD = 200

# scrypt cost: 16 MB of memory and ~50 ms per hash, so guessing passwords offline is slow.
_N, _R, _P = 2**14, 8, 1


# --- passwords -----------------------------------------------------------------------------


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=32)
    return f"scrypt${_N}${_R}${_P}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt, digest = stored.split("$")
        if scheme != "scrypt":
            return False
        got = hashlib.scrypt(password.encode(), salt=_unb64(salt), n=int(n), r=int(r), p=int(p), dklen=32)
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(got, _unb64(digest))


# A real hash to check against when the username doesn't exist, so a wrong username takes as long
# as a wrong password (no telling which usernames exist from the response time).
_DUMMY_HASH = hash_password(secrets.token_urlsafe(16))


def clean_username(username: str) -> str:
    name = username.strip().lower()
    if not USERNAME_RE.match(name):
        raise RuleError("Usernames are 3-24 characters: letters, numbers, dots, dashes or underscores")
    return name


def check_password(password: str) -> None:
    if len(password) < MIN_PASSWORD:
        raise RuleError(f"Passwords need at least {MIN_PASSWORD} characters")
    if len(password) > MAX_PASSWORD:
        raise RuleError(f"Passwords can be at most {MAX_PASSWORD} characters")


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


# --- accounts ------------------------------------------------------------------------------


def user_count(session: Session) -> int:
    return session.exec(select(func.count()).select_from(User)).one()


def find_user(session: Session, username: str) -> User | None:
    return session.exec(select(User).where(User.username == username.strip().lower())).first()


def create_user(session: Session, username: str, password: str, is_admin: bool = False) -> User:
    name = clean_username(username)
    check_password(password)
    if find_user(session, name):
        raise RuleError("That username is taken", 409)
    user = User(username=name, password_hash=hash_password(password), is_admin=is_admin)
    session.add(user)
    session.flush()
    return user


def membership(session: Session, group_id: int, user_id: int) -> GroupMember | None:
    return session.get(GroupMember, (group_id, user_id))


def memberships(session: Session, user_id: int) -> list[GroupMember]:
    return list(session.exec(select(GroupMember).where(GroupMember.user_id == user_id).order_by(col(GroupMember.joined_at))).all())


def player_claimed(session: Session, player_id: int) -> bool:
    return session.exec(select(GroupMember.user_id).where(GroupMember.player_id == player_id)).first() is not None


def join_group(session: Session, user: User, group: Group, role: str = "member", player_id: int | None = None) -> GroupMember:
    """Add an account to a group, optionally as one of its players."""
    if membership(session, group.id, user.id):
        raise RuleError("You're already in this group", 409)
    if player_id is not None:
        player = session.get(Player, player_id)
        if player is None or player.group_id != group.id:
            raise RuleError("That player isn't in this group", 404)
        if player_claimed(session, player_id):
            raise RuleError("Someone already plays as that player", 409)
    m = GroupMember(group_id=group.id, user_id=user.id, role=role, player_id=player_id)
    session.add(m)
    session.flush()
    return m


def clean_group_name(name: str) -> str:
    name = " ".join((name or "").split())
    if not 2 <= len(name) <= 40:
        raise RuleError("Group names are 2-40 characters")
    return name


def create_group(session: Session, owner: User, name: str) -> Group:
    """A new group owned by `owner`, with its own settings."""
    group = Group(name=clean_group_name(name), owner_user_id=owner.id)
    session.add(group)
    session.flush()
    session.add(AppSettings(group_id=group.id))
    join_group(session, owner, group, role="owner")
    return group


def set_up_owner(session: Session, username: str, password: str, player_id: int | None) -> User:
    """The very first account: the site admin. It takes over the group that already exists (data
    from before accounts), or starts one."""
    if user_count(session):
        raise RuleError("This site is already set up. Sign in instead.", 409)
    user = create_user(session, username, password, is_admin=True)
    group = session.exec(select(Group).order_by(col(Group.id))).first()
    if group is None:
        group = create_group(session, user, f"{user.username}'s group")
    else:
        group.owner_user_id = user.id
        session.add(group)
        if session.exec(select(AppSettings).where(AppSettings.group_id == group.id)).first() is None:
            session.add(AppSettings(group_id=group.id))
        join_group(session, user, group, role="owner")
    if player_id is not None:
        m = membership(session, group.id, user.id)
        player = session.get(Player, player_id)
        if player is None or player.group_id != group.id:
            raise RuleError("That player doesn't exist", 404)
        m.player_id = player_id
        session.add(m)
    for run in session.exec(select(Run).where(Run.group_id == group.id, col(Run.owner_user_id).is_(None))).all():
        run.owner_user_id = user.id
        session.add(run)
    session.flush()
    return user


def authenticate(session: Session, username: str, password: str) -> User | None:
    user = find_user(session, username)
    if user is None:
        verify_password(password, _DUMMY_HASH)
        return None
    return user if verify_password(password, user.password_hash) else None


def change_password(session: Session, user: User, current: str, new: str) -> None:
    if not verify_password(current, user.password_hash):
        raise RuleError("Your current password is wrong", 403)
    check_password(new)
    user.password_hash = hash_password(new)
    session.add(user)
    # Sign out every other browser: a password change is often because one was lost or shared.
    session.exec(delete(AuthSession).where(col(AuthSession.user_id) == user.id))


def remove_member(session: Session, group: Group, user: User) -> None:
    """Take an account out of a group. Their player, games, gold and items stay with the group (the
    player can be invited again). An account left in no group is deleted, so its username is free."""
    m = membership(session, group.id, user.id)
    if m is None:
        raise RuleError("They aren't in this group", 404)
    if m.role == "owner":
        raise RuleError("The group's owner can't be removed", 409)
    for run in session.exec(select(Run).where(Run.group_id == group.id, Run.owner_user_id == user.id)).all():
        run.owner_user_id = None  # the group owner still manages it
        session.add(run)
    for row in session.exec(select(AuthSession).where(AuthSession.user_id == user.id, AuthSession.group_id == group.id)).all():
        row.group_id = None
        session.add(row)
    session.delete(m)
    session.flush()
    if not memberships(session, user.id) and not user.is_admin:
        delete_user(session, user)


def delete_user(session: Session, user: User) -> None:
    """Remove an account entirely. It can't own a group (hand the group over or delete it first)."""
    if session.exec(select(Group.id).where(Group.owner_user_id == user.id)).first():
        raise RuleError("This account owns a group", 409)
    session.exec(delete(AuthSession).where(col(AuthSession.user_id) == user.id))
    session.exec(delete(GroupMember).where(col(GroupMember.user_id) == user.id))
    for run in session.exec(select(Run).where(Run.owner_user_id == user.id)).all():
        run.owner_user_id = None
        session.add(run)
    for model in (Invite, SiteInvite):
        for inv in session.exec(select(model).where(model.created_by_user_id == user.id)).all():
            session.delete(inv)
        for inv in session.exec(select(model).where(model.used_by_user_id == user.id)).all():
            inv.used_by_user_id = None
            session.add(inv)
    session.flush()
    session.delete(user)
    session.flush()


# --- sessions ------------------------------------------------------------------------------


def start_session(session: Session, user: User) -> str:
    """Sign a browser in. Returns the raw token for the cookie. It starts in the user's first group."""
    token = secrets.token_urlsafe(32)
    now = utcnow()
    first = next(iter(memberships(session, user.id)), None)
    session.add(
        AuthSession(
            token_hash=_token_hash(token),
            user_id=user.id,
            expires_at=now + timedelta(days=SESSION_DAYS),
            group_id=first.group_id if first else None,
        )
    )
    user.last_login_at = now
    session.add(user)
    # Tidy up: drop this account's expired sessions.
    session.exec(
        delete(AuthSession).where(col(AuthSession.user_id) == user.id, col(AuthSession.expires_at) < now)
    )
    return token


def session_for_token(session: Session, token: str | None) -> AuthSession | None:
    if not token:
        return None
    row = session.get(AuthSession, _token_hash(token))
    if row is None:
        return None
    if row.expires_at < datetime.now(UTC):
        session.delete(row)
        session.commit()
        return None
    return row


def user_for_token(session: Session, token: str | None) -> User | None:
    row = session_for_token(session, token)
    return session.get(User, row.user_id) if row else None


def end_session(session: Session, token: str | None) -> None:
    if token:
        row = session.get(AuthSession, _token_hash(token))
        if row:
            session.delete(row)


def switch_group(session: Session, token: str | None, user: User, group_id: int) -> None:
    if membership(session, group_id, user.id) is None:
        raise RuleError("You aren't in that group", 404)
    row = session_for_token(session, token)
    if row is not None:
        row.group_id = group_id
        session.add(row)


# --- player invites (join a group as one of its players) -------------------------------------


def create_invite(session: Session, group: Group, player_id: int, by: User) -> tuple[Invite, str]:
    """A one-time link for one of the group's players. Replaces older links for that player."""
    player = session.get(Player, player_id)
    if player is None or player.group_id != group.id:
        raise RuleError("That player doesn't exist", 404)
    if player_claimed(session, player_id):
        raise RuleError("That player already has an account. Remove it first to invite someone new.", 409)
    for old in open_invites(session, group.id, player_id):
        old.revoked = True
        session.add(old)
    token = secrets.token_urlsafe(24)
    invite = Invite(
        token_hash=_token_hash(token),
        group_id=group.id,
        player_id=player_id,
        created_by_user_id=by.id,
        expires_at=utcnow() + timedelta(days=INVITE_DAYS),
    )
    session.add(invite)
    session.flush()
    return invite, token


def open_invites(session: Session, group_id: int, player_id: int | None = None) -> list[Invite]:
    query = select(Invite).where(
        Invite.group_id == group_id,
        col(Invite.used_at).is_(None),
        Invite.revoked == False,  # noqa: E712
        col(Invite.expires_at) > utcnow(),
    )
    if player_id is not None:
        query = query.where(Invite.player_id == player_id)
    return list(session.exec(query).all())


def invite_for_token(session: Session, token: str) -> Invite:
    invite = session.exec(select(Invite).where(Invite.token_hash == _token_hash(token))).first()
    if invite is None or invite.revoked:
        raise RuleError("This invite link isn't valid. Ask the group's owner for a new one.", 404)
    if invite.used_at is not None:
        raise RuleError("This invite link has already been used. Sign in instead.", 410)
    if invite.expires_at < datetime.now(UTC):
        raise RuleError("This invite link has expired. Ask the group's owner for a new one.", 410)
    return invite


def _use_invite(session: Session, invite: Invite, user: User) -> None:
    join_group(session, user, session.get(Group, invite.group_id), player_id=invite.player_id)
    invite.used_at = utcnow()
    invite.used_by_user_id = user.id
    session.add(invite)


def accept_invite(session: Session, token: str, username: str, password: str) -> User:
    """Sign up from an invite link: a new account in that group, as that player."""
    invite = invite_for_token(session, token)
    user = create_user(session, username, password)
    _use_invite(session, invite, user)
    return user


def accept_invite_signed_in(session: Session, token: str, user: User) -> GroupMember:
    """Join another group with the account you already have."""
    invite = invite_for_token(session, token)
    _use_invite(session, invite, user)
    return membership(session, invite.group_id, user.id)


# --- site invites (start a new group) ---------------------------------------------------------


def site_settings(session: Session) -> SiteSettings:
    row = session.get(SiteSettings, 1)
    if row is None:
        row = SiteSettings(id=1)
        session.add(row)
        session.flush()
    return row


def create_site_invite(session: Session, by: User, note: str = "") -> tuple[SiteInvite, str]:
    token = secrets.token_urlsafe(18)
    inv = SiteInvite(
        token_hash=_token_hash(token),
        note=note.strip()[:80],
        created_by_user_id=by.id,
        expires_at=utcnow() + timedelta(days=SITE_INVITE_DAYS),
    )
    session.add(inv)
    session.flush()
    return inv, token


def open_site_invites(session: Session) -> list[SiteInvite]:
    return list(
        session.exec(
            select(SiteInvite).where(
                col(SiteInvite.used_at).is_(None), SiteInvite.revoked == False, col(SiteInvite.expires_at) > utcnow()  # noqa: E712
            )
        ).all()
    )


def site_invite_for_token(session: Session, token: str) -> SiteInvite:
    inv = session.exec(select(SiteInvite).where(SiteInvite.token_hash == _token_hash(token.strip()))).first()
    if inv is None or inv.revoked:
        raise RuleError("That invite code isn't valid.", 404)
    if inv.used_at is not None:
        raise RuleError("That invite code has already been used.", 410)
    if inv.expires_at < datetime.now(UTC):
        raise RuleError("That invite code has expired.", 410)
    return inv


def can_start_group(session: Session, user: User | None, code: str | None) -> SiteInvite | None:
    """Starting a group needs open sign-up, a site invite code, or being the site admin.
    Returns the invite to mark used (None when no code was needed). Raises when not allowed."""
    if code:
        return site_invite_for_token(session, code)
    if site_settings(session).open_signup or (user is not None and user.is_admin):
        return None
    raise RuleError("Starting a group needs an invite code for now.", 403)


def start_group(session: Session, user: User, name: str, code: str | None) -> Group:
    inv = can_start_group(session, user, code)
    group = create_group(session, user, name)
    if inv is not None:
        inv.used_at = utcnow()
        inv.used_by_user_id = user.id
        session.add(inv)
    return group


def sign_up(session: Session, username: str, password: str, group_name: str, code: str | None) -> User:
    """A new account that starts its own group (with a site invite code, or while sign-up is open)."""
    inv = can_start_group(session, None, code)
    user = create_user(session, username, password)
    create_group(session, user, group_name)
    if inv is not None:
        inv.used_at = utcnow()
        inv.used_by_user_id = user.id
        session.add(inv)
    return user


# --- sign-in throttle ----------------------------------------------------------------------


class LoginThrottle:
    """Slows down password guessing: after `limit` misses in 15 minutes, that key has to wait.

    Keys are "address|username" (5 tries) and the address alone (20 tries), so a stranger who
    guesses at someone's account only locks themselves out, not the account's owner.
    """

    def __init__(self, limit: int = 5, window: float = 15 * 60, clock=time.monotonic):
        self.limit, self.window, self.clock = limit, window, clock
        self._misses: dict[str, deque[float]] = defaultdict(deque)

    def _recent(self, key: str) -> deque[float]:
        q, cutoff = self._misses[key], self.clock() - self.window
        while q and q[0] < cutoff:
            q.popleft()
        return q

    def wait_seconds(self, key: str) -> int:
        q = self._recent(key)
        return max(1, int(q[0] + self.window - self.clock())) if len(q) >= self.limit else 0

    def miss(self, key: str) -> None:
        self._recent(key).append(self.clock())

    def clear(self, key: str) -> None:
        self._misses.pop(key, None)


pair_throttle = LoginThrottle(limit=5)
address_throttle = LoginThrottle(limit=20)
signup_throttle = LoginThrottle(limit=5, window=60 * 60)  # new accounts per address per hour
