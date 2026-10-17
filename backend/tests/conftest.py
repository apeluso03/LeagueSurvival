import os

os.environ.setdefault("STARTUP_TASKS", "false")
os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ["RIOT_API_KEY"] = ""  # tests must never call the real Riot API

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.models import AppSettings, Champion, Player, User
from app.services import auth


def make_champions(n: int) -> list[Champion]:
    return [Champion(id=f"Champ{i:03d}", key=1000 + i, name=f"Champ {i}", tags=["Fighter"]) for i in range(n)]


@pytest.fixture
def engine():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(eng)
    return eng


@pytest.fixture
def session(engine):
    with Session(engine) as s:
        s.add_all(make_champions(20))
        s.add_all([Player(display_name=name) for name in ("Alex", "Bea", "Cal", "Dee", "Eli", "Fay")])
        s.add(AppSettings())
        s.commit()
        yield s


TEST_PASSWORD = "correct horse battery"
_HASH = None


def make_user(session: Session, username: str, player_id: int | None = None, is_admin: bool = False) -> User:
    """An account straight in the database (hashing once per test run keeps the suite fast)."""
    global _HASH
    if _HASH is None:
        _HASH = auth.hash_password(TEST_PASSWORD)
    user = User(username=username, password_hash=_HASH, player_id=player_id, is_admin=is_admin)
    session.add(user)
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
    return make_user(session, "owner", is_admin=True)


@pytest.fixture
def client(owner, sign_in):
    return sign_in(owner)
