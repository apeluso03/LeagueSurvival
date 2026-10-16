from datetime import UTC, datetime

from app.services import achievements, shame
from tests.test_api import _play, create_run


def test_achievements_from_history(client):
    rid = create_run(client)["id"]
    lost = _play(client, rid, "loss")
    for _ in range(3):
        _play(client, rid, "win")
    report = client.get("/api/achievements").json()
    assert {a["id"] for a in report["catalog"]} >= {"first_win", "streak3", "patient_zero", "penta"}
    mine = {u["id"]: u for u in report["players"]["1"]}
    assert {"first_win", "streak3"} <= set(mine)
    first_elim_player = next(a["player_id"] for a in lost["assignments"] if a["played_champion_id"] == lost["eliminated"][0])
    assert "patient_zero" in {u["id"] for u in report["players"][str(first_elim_player)]}
    assert report["rarity"]["first_win"] == 1.0  # both players who played have it
    assert report["rarity"]["penta"] == 0.0


def test_undo_takes_an_achievement_back(client, session):
    rid = create_run(client)["id"]
    game = _play(client, rid, "win")
    assert "first_win" in achievements.evaluate(session).get(1, {})
    client.post(f"/api/games/{game['id']}/undo")
    session.expire_all()
    assert "first_win" not in achievements.evaluate(session).get(1, {})


def test_title_must_be_earned(client):
    rid = create_run(client)["id"]
    assert client.patch("/api/players/1", json={"title": "first_win"}).status_code == 400
    _play(client, rid, "win")
    r = client.patch("/api/players/1", json={"title": "first_win", "color": "#ff4655"})
    assert r.status_code == 200 and r.json()["title"] == "first_win" and r.json()["color"] == "#ff4655"
    assert client.patch("/api/players/1", json={"color": "red"}).status_code == 422
    assert client.patch("/api/players/1", json={"title": None, "color": None}).json()["color"] is None


def test_hall_of_shame_and_cursed_champions(client):
    rid = create_run(client, champion_ids=[f"Champ00{i}" for i in range(1, 7)])["id"]
    s = client.get("/api/shame", params={"run_id": rid}).json()
    assert s["worst_games"] == [] and s["cursed_champions"] == []
    _play(client, rid, "loss")
    s = client.get("/api/shame", params={"run_id": rid}).json()
    assert {r["player_id"] for r in s["reapers"]} == {1, 2}
    assert s["cursed_champions"] == []  # one game each isn't a curse yet, and winners never are
    assert client.get("/api/shame", params={"run_id": 999}).status_code == 404


def test_wrapped_for_a_month(client):
    rid = create_run(client)["id"]
    _play(client, rid, "win")
    _play(client, rid, "loss")
    month = datetime.now(UTC).strftime("%Y-%m")
    w = client.get("/api/wrapped").json()
    assert w["month"] == month and month in w["months"]
    assert (w["games"], w["wins"], w["best_streak"], w["champions_lost"]) == (2, 1, 1, 2)
    assert w["best_duo"] == {"players": [1, 2], "games": 2, "wins": 1}
    assert w["worst_duo"] is None  # the only duo is already the best one
    assert {p["player_id"] for p in w["players"]} == {1, 2}
    assert w["most_played"] is not None and w["mvp"] is not None
    empty = client.get("/api/wrapped", params={"month": "2001-01"}).json()
    assert empty["games"] == 0 and empty["mvp"] is None
    assert client.get("/api/wrapped", params={"month": "nope"}).status_code == 400


def test_month_bounds_wrap_the_year():
    start, end = shame.month_bounds("2026-12")
    assert start == datetime(2026, 12, 1, tzinfo=UTC) and end == datetime(2027, 1, 1, tzinfo=UTC)
