import os

os.environ.setdefault("STARTUP_TASKS", "false")
os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ["RIOT_API_KEY"] = ""  # tests must never call the real Riot API

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.models import AppSettings, Champion, Group, GroupMember, Player, SiteSettings, User
from app.services import auth


def make_champions(n: int) -> list[Champion]:
    return [Champion(id=f"Champ{i:03d}", key=1000 + i, name=f"Champ {i}", tags=["Fighter"]) for i in range(n)]


# TEST_DATABASE_URL=postgresql+psycopg://... runs the suite on Postgres (a throwaway database: every
# table is dropped and made again for each test). Default: an in-memory SQLite database.
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "")


@pytest.fixture
def engine():
    if TEST_DATABASE_URL:
        eng = create_engine(TEST_DATABASE_URL)
        SQLModel.metadata.drop_all(eng)
        SQLModel.metadata.create_all(eng)
        yield eng
        eng.dispose()
        return
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(eng)
    yield eng


def _resync_ids(session: Session) -> None:
    """Postgres: rows added with explicit ids don't move the id counters; catch them up."""
    if session.get_bind().dialect.name != "postgresql":
        return
    from sqlalchemy import Integer, text

    for table in SQLModel.metadata.sorted_tables:
        if "id" not in table.c or len(table.primary_key.columns) != 1 or not isinstance(table.c.id.type, Integer):
            continue
        quoted = '"' + table.name + '"'  # "user" and "group" are reserved words
        seq = session.exec(text(f"SELECT pg_get_serial_sequence('{quoted}', 'id')")).one()[0]
        if seq:
            session.exec(text(f"SELECT setval('{seq}', COALESCE((SELECT MAX(id) FROM {quoted}), 0) + 1, false)"))
    session.commit()


@pytest.fixture
def session(engine):
    with Session(engine) as s:
        s.add_all(make_champions(20))
        s.add(Group(id=GROUP, name="Test group"))
        s.flush()
        s.add_all([Player(display_name=name, group_id=GROUP) for name in ("Alex", "Bea", "Cal", "Dee", "Eli", "Fay")])
        s.add(AppSettings(group_id=GROUP))
        s.add(SiteSettings(id=1))
        s.commit()
        _resync_ids(s)
        yield s


GROUP = 1  # the test group every fixture player is in
TEST_PASSWORD = "correct horse battery"
_HASH = None


def make_user(
    session: Session,
    username: str,
    player_id: int | None = None,
    is_admin: bool = False,
    role: str | None = "member",
    group_id: int = GROUP,
) -> User:
    """An account straight in the database (hashing once per test run keeps the suite fast), in
    the test group as `role` (None: in no group), playing as `player_id`."""
    global _HASH
    if _HASH is None:
        _HASH = auth.hash_password(TEST_PASSWORD)
    user = User(username=username, password_hash=_HASH, is_admin=is_admin)
    session.add(user)
    session.flush()
    if role is not None:
        session.add(GroupMember(group_id=group_id, user_id=user.id, role=role, player_id=player_id))
        if role == "owner":
            group = session.get(Group, group_id)
            group.owner_user_id = user.id
            session.add(group)
    session.commit()
    session.refresh(user)
    return user


@pytest.fixture
def anon_client(engine, session):
    """A signed-out browser."""
    from app.db import get_session
    from app.main import app

    def _override():
        with Session(engine) as s:
            yield s

    auth.pair_throttle.__init__(limit=5)
    auth.address_throttle.__init__(limit=20)
    auth.signup_throttle.__init__(limit=5, window=60 * 60)
    app.dependency_overrides[get_session] = _override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def sign_in(engine, anon_client):
    """sign_in(user) -> a TestClient signed in as that user (its own cookie jar)."""
    from app.main import app

    clients = []

    def _sign_in(user: User) -> TestClient:
        with Session(engine) as s:
            token = auth.start_session(s, s.get(User, user.id))
            s.commit()
        c = TestClient(app)
        c.cookies.set(auth.SESSION_COOKIE, token)
        clients.append(c)
        return c

    yield _sign_in
    for c in clients:
        c.close()


@pytest.fixture
def owner(session) -> User:
    """The site owner: the account most tests act as."""
    return make_user(session, "owner", is_admin=True, role="owner")


@pytest.fixture
def client(owner, sign_in):
    return sign_in(owner)
