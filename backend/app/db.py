from collections.abc import Iterator

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlmodel import Session, create_engine

from app.config import get_settings


def make_engine(url: str) -> Engine:
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    eng = create_engine(url, connect_args=connect_args)
    if url.startswith("sqlite"):

        @event.listens_for(eng, "connect")
        def _fk_on(dbapi_conn, _record):  # pragma: no cover - trivial
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.close()

    return eng


engine = make_engine(get_settings().database_url)


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
