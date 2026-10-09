import os

os.environ.setdefault("STARTUP_TASKS", "false")
os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ["RIOT_API_KEY"] = ""  # tests must never call the real Riot API

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.models import AppSettings, Champion, Player


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


@pytest.fixture
def client(engine, session):
    from app.db import get_session
    from app.main import app

    def _override():
        with Session(engine) as s:
            yield s

    app.dependency_overrides[get_session] = _override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
