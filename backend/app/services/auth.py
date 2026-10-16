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

from app.models import AuthSession, Invite, Player, Run, User, utcnow
from app.services.rules import RuleError

SESSION_COOKIE = "lst_session"
SESSION_DAYS = 30
INVITE_DAYS = 7

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


def create_user(session: Session, username: str, password: str, player_id: int | None, is_admin: bool = False) -> User:
    name = clean_username(username)
    check_password(password)
    if find_user(session, name):
        raise RuleError("That username is taken", 409)
    if player_id is not None:
        if session.get(Player, player_id) is None:
            raise RuleError("That player doesn't exist", 404)
        if session.exec(select(User.id).where(User.player_id == player_id)).first():
            raise RuleError("Someone already plays as that player", 409)
    user = User(username=name, password_hash=hash_password(password), player_id=player_id, is_admin=is_admin)
    session.add(user)
    session.flush()
    return user


def set_up_owner(session: Session, username: str, password: str, player_id: int | None) -> User:
    """The very first account: the site owner. It takes over every run made before logins existed."""
    if user_count(session):
        raise RuleError("This site is already set up. Sign in instead.", 409)
    user = create_user(session, username, password, player_id, is_admin=True)
    for run in session.exec(select(Run).where(col(Run.owner_user_id).is_(None))).all():
        run.owner_user_id = user.id
        session.add(run)
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


def delete_user(session: Session, user: User) -> None:
    """Remove an account. Their player, games, gold and items stay; the player can be invited again."""
    session.exec(delete(AuthSession).where(col(AuthSession.user_id) == user.id))
    for run in session.exec(select(Run).where(Run.owner_user_id == user.id)).all():
        run.owner_user_id = None  # site owners still manage it
        session.add(run)
    for invite in session.exec(select(Invite).where(Invite.created_by_user_id == user.id)).all():
        session.delete(invite)
    for invite in session.exec(select(Invite).where(Invite.used_by_user_id == user.id)).all():
        invite.used_by_user_id = None
        session.add(invite)
    session.delete(user)


# --- sessions ------------------------------------------------------------------------------


def start_session(session: Session, user: User) -> str:
    """Sign a browser in. Returns the raw token for the cookie."""
    token = secrets.token_urlsafe(32)
    now = utcnow()
    session.add(AuthSession(token_hash=_token_hash(token), user_id=user.id, expires_at=now + timedelta(days=SESSION_DAYS)))
    user.last_login_at = now
    session.add(user)
    # Tidy up: drop this account's expired sessions.
    session.exec(
        delete(AuthSession).where(col(AuthSession.user_id) == user.id, col(AuthSession.expires_at) < now)
    )
    return token


def user_for_token(session: Session, token: str | None) -> User | None:
    if not token:
        return None
    row = session.get(AuthSession, _token_hash(token))
    if row is None:
        return None
    if row.expires_at < datetime.now(UTC):
        session.delete(row)
        session.commit()
        return None
    return session.get(User, row.user_id)


def end_session(session: Session, token: str | None) -> None:
    if token:
        row = session.get(AuthSession, _token_hash(token))
        if row:
            session.delete(row)


# --- invites -------------------------------------------------------------------------------


def create_invite(session: Session, player_id: int, by: User) -> tuple[Invite, str]:
    """A one-time sign-up link for a player who doesn't have an account yet. Replaces older links."""
    if session.get(Player, player_id) is None:
        raise RuleError("That player doesn't exist", 404)
    if session.exec(select(User.id).where(User.player_id == player_id)).first():
        raise RuleError("That player already has an account. Remove it first to invite someone new.", 409)
    for old in open_invites(session, player_id):
        old.revoked = True
        session.add(old)
    token = secrets.token_urlsafe(24)
    invite = Invite(
        token_hash=_token_hash(token),
        player_id=player_id,
        created_by_user_id=by.id,
        expires_at=utcnow() + timedelta(days=INVITE_DAYS),
    )
    session.add(invite)
    session.flush()
    return invite, token


def open_invites(session: Session, player_id: int | None = None) -> list[Invite]:
    query = select(Invite).where(
        col(Invite.used_at).is_(None), Invite.revoked == False, col(Invite.expires_at) > utcnow()  # noqa: E712
    )
    if player_id is not None:
        query = query.where(Invite.player_id == player_id)
    return list(session.exec(query).all())


def invite_for_token(session: Session, token: str) -> Invite:
    invite = session.exec(select(Invite).where(Invite.token_hash == _token_hash(token))).first()
    if invite is None or invite.revoked:
        raise RuleError("This invite link isn't valid. Ask the owner for a new one.", 404)
    if invite.used_at is not None:
        raise RuleError("This invite link has already been used. Sign in instead.", 410)
    if invite.expires_at < datetime.now(UTC):
        raise RuleError("This invite link has expired. Ask the owner for a new one.", 410)
    return invite


def accept_invite(session: Session, token: str, username: str, password: str) -> User:
    invite = invite_for_token(session, token)
    user = create_user(session, username, password, invite.player_id)
    invite.used_at = utcnow()
    invite.used_by_user_id = user.id
    session.add(invite)
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
