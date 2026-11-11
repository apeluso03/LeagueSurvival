"""Live updates (SPEC 12.3): the WebSocket, events pushed after commit, and the "changed" ping."""

import asyncio

import pytest
from sqlmodel import Session
from starlette.websockets import WebSocketDisconnect

from app.models import Group
from app.services import hub as hub_mod
from app.services import rules
from app.services.events import emit
from app.services.hub import hub
from tests.conftest import GROUP, make_user


def next_of(ws, type_: str, limit: int = 5) -> dict:
    """The next message of this type (skipping others, like "changed" after an event)."""
    for _ in range(limit):
        msg = ws.receive_json()
        if msg["type"] == type_:
            return msg
    raise AssertionError(f"no {type_} message")


@pytest.fixture
def run(session):
    r = rules.create_run(session, "Run", 3, group_id=GROUP)
    session.commit()
    return r


def test_spin_reaches_other_browsers_with_its_origin(client, sign_in, session, run):
    member = make_user(session, "bea", player_id=2)
    watcher = sign_in(member)
    with watcher.websocket_connect("/api/ws") as ws:
        assert ws.receive_json() == {"type": "hello", "group_id": GROUP}
        res = client.post(f"/api/runs/{run.id}/spins", json={"player_ids": [1, 2]}, headers={"X-Client-Id": "tab-1"})
        assert res.status_code == 200
        spin = next_of(ws, "spin")
        assert spin == {"type": "spin", "origin": "tab-1", "game_id": res.json()["game"]["id"], "run_id": run.id}
        assert next_of(ws, "changed")["origin"] == "tab-1"
        # Reading changes nothing, and a refused change says nothing: the next message is the result.
        client.get(f"/api/runs/{run.id}")
        assert client.post(f"/api/runs/{run.id}/spins", json={"player_ids": [1, 2]}).status_code == 409
        game_id = res.json()["game"]["id"]
        assert client.post(f"/api/games/{game_id}/result", json={"result": "void"}).status_code == 200
        assert ws.receive_json()["type"] == "result"
        assert ws.receive_json()["type"] == "changed"  # read everything sent before closing the socket


def test_signed_out_and_other_sites_are_refused(anon_client, client):
    with pytest.raises(WebSocketDisconnect) as e:
        with anon_client.websocket_connect("/api/ws") as ws:
            ws.receive_json()
    assert e.value.code == 4401
    with pytest.raises(WebSocketDisconnect) as e:
        with client.websocket_connect("/api/ws", headers={"origin": "https://evil.example"}) as ws:
            ws.receive_json()
    assert e.value.code == 1008


def test_other_groups_hear_nothing(engine, session, sign_in, client, run):
    session.add(Group(id=2, name="Other"))
    session.commit()
    stranger = sign_in(make_user(session, "zed", role="owner", group_id=2))
    with stranger.websocket_connect("/api/ws") as ws:
        assert ws.receive_json()["group_id"] == 2
        assert client.post(f"/api/runs/{run.id}/spins", json={"player_ids": [1, 2]}).status_code == 200
        hub.publish(2, {"type": "marker"})
        assert ws.receive_json() == {"type": "marker"}  # nothing from group 1's spin came first


def test_events_go_out_after_commit_only(engine):
    async def scenario():
        q = hub.subscribe(GROUP)
        try:
            with Session(engine) as s:
                emit(s, GROUP, "spin", game_id=5, run_id=1, secret="x")
                s.rollback()
                emit(s, GROUP, "result", game_id=5, run_id=1, secret="x")
                token = hub_mod.ORIGIN.set("tab-9")
                s.commit()
                hub_mod.ORIGIN.reset(token)
            await asyncio.sleep(0)
            msgs = []
            while not q.empty():
                msgs.append(q.get_nowait())
            return msgs
        finally:
            hub.unsubscribe(GROUP, q)

    with Session(engine) as s:
        s.add(Group(id=GROUP, name="G"))
        s.commit()
    # Only the committed one, with ids only (nothing else from the payload).
    assert asyncio.run(scenario()) == [{"type": "result", "origin": "tab-9", "game_id": 5, "run_id": 1}]
