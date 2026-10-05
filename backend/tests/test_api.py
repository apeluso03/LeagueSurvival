def create_run(client, **kw):
    r = client.post("/api/runs", json={"name": "Run 1", **kw})
    assert r.status_code == 201, r.text
    return r.json()


def test_full_manual_loop(client):
    run = create_run(client)
    assert run["alive_count"] == run["total_count"] == 20
    assert client.get("/api/settings").json()["active_run_id"] == run["id"]

    spin = client.post(f"/api/runs/{run['id']}/spins", json={"player_ids": [1, 2, 3]}).json()
    assert spin["practice"] is False
    game = spin["game"]
    assert len(game["assignments"]) == 3
    assert client.get("/api/settings").json()["last_used_player_ids"] == [1, 2, 3]

    # Second spin is blocked while one is pending
    r = client.post(f"/api/runs/{run['id']}/spins", json={"player_ids": [1, 2]})
    assert r.status_code == 409

    picks = [{"player_id": a["player_id"], "option_index": 0} for a in game["assignments"]]
    game = client.patch(f"/api/games/{game['id']}/assignments", json={"picks": picks}).json()
    assert all(a["played_champion_id"] == a["options"][0] for a in game["assignments"])

    game = client.post(f"/api/games/{game['id']}/result", json={"result": "loss"}).json()
    assert game["status"] == "lost" and game["result_source"] == "manual"
    assert sorted(game["eliminated"]) == sorted(a["options"][0] for a in game["assignments"])

    run = client.get(f"/api/runs/{run['id']}").json()
    assert run["alive_count"] == 17 and run["games_played"] == 1

    alive = client.get(f"/api/runs/{run['id']}/pool", params={"include_eliminated": False}).json()
    assert len(alive) == 17 and all(e["status"] == "alive" for e in alive)

    game = client.post(f"/api/games/{game['id']}/undo").json()
    assert game["status"] == "pending" and game["eliminated"] == []
    assert client.get(f"/api/runs/{run['id']}").json()["alive_count"] == 20


def test_rule_errors_return_json(client):
    run = create_run(client)
    r = client.post(f"/api/runs/{run['id']}/spins", json={"player_ids": [1]})
    assert r.status_code == 400 and "players" in r.json()["detail"]


def test_practice_spin_saves_nothing(client):
    run = create_run(client)
    client.patch("/api/settings", json={"challenge_mode": False})
    spin = client.post(f"/api/runs/{run['id']}/spins", json={"player_ids": [1, 2]}).json()
    assert spin["practice"] is True and spin["game"] is None and len(spin["assignments"]) == 2
    assert client.get("/api/games", params={"run_id": run["id"]}).json() == []


def test_turning_off_challenge_mode_can_void_pending(client):
    run = create_run(client)
    game = client.post(f"/api/runs/{run['id']}/spins", json={"player_ids": [1, 2]}).json()["game"]
    client.patch("/api/settings", json={"challenge_mode": False, "void_pending": True})
    game = client.get(f"/api/games/{game['id']}").json()
    assert game["status"] == "void" and game["void_reason"] == "challenge mode turned off"


def test_token_revive_flow(client):
    run = create_run(client)
    rid = run["id"]
    client.post(f"/api/runs/{rid}/pool/Champ000/eliminate")
    for _ in range(3):
        game = client.post(f"/api/runs/{rid}/spins", json={"player_ids": [1, 2]}).json()["game"]
        game = client.post(f"/api/games/{game['id']}/result", json={"result": "win"}).json()
    assert sorted(game["tokens_earned"]) == [1, 2]
    tokens = client.get("/api/tokens", params={"run_id": rid, "unused_only": True}).json()
    assert len(tokens) == 2

    r = client.post(f"/api/runs/{rid}/pool/Champ000/revive", json={"token_id": tokens[0]["id"]})
    assert r.status_code == 200 and r.json()["tokens_available"] == 1
    assert r.json()["alive_count"] == 20


def test_player_crud(client):
    p = client.post("/api/players", json={"display_name": "Gus", "riot_game_name": "Gus", "riot_tag_line": "NA1"})
    assert p.status_code == 201
    pid = p.json()["id"]
    assert client.patch(f"/api/players/{pid}", json={"display_name": "Gus2"}).json()["display_name"] == "Gus2"
    assert client.delete(f"/api/players/{pid}").status_code == 204


def test_player_with_history_cannot_be_deleted(client):
    run = create_run(client)
    client.post(f"/api/runs/{run['id']}/spins", json={"player_ids": [1, 2]})
    assert client.delete("/api/players/1").status_code == 409


def test_ddragon_parsing():
    from app.services.ddragon import parse_champions

    data = {
        "data": {
            "MonkeyKing": {
                "id": "MonkeyKing",
                "key": "62",
                "name": "Wukong",
                "title": "the Monkey King",
                "tags": ["Fighter", "Tank"],
                "image": {"full": "MonkeyKing.png"},
            }
        }
    }
    [c] = parse_champions(data, "14.1.1", "https://dd")
    assert (c.id, c.key, c.name) == ("MonkeyKing", 62, "Wukong")
    assert c.image_url == "https://dd/cdn/14.1.1/img/champion/MonkeyKing.png"


# --- Riot linking, sync and stats (M3) ---------------------------------------------

import pytest  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.models import Player  # noqa: E402
from app.services.riot_client import RiotError  # noqa: E402
from tests.factories import FakeRiotClient, P, make_match  # noqa: E402


@pytest.fixture
def fake_riot(monkeypatch):
    """Pretend a key is set and route every Riot call to a FakeRiotClient."""
    fake = FakeRiotClient(
        accounts={("Gus", "NA1"): "puuid-gus"},
        matches={"NA1_1": make_match("NA1_1", [P("puuid-gus", 1001, kills=4, deaths=1, assists=2)])},
    )
    monkeypatch.setattr(get_settings(), "riot_api_key", "RGAPI-test")
    for module in ("app.routers.players", "app.routers.riot"):
        monkeypatch.setattr(f"{module}.RiotClient", lambda *a, **k: fake)
    return fake


def test_create_player_links_riot_id(client, fake_riot):
    p = client.post("/api/players", json={"display_name": "Gus", "riot_game_name": "gus", "riot_tag_line": "na1"})
    assert p.status_code == 201
    assert p.json()["puuid"] == "puuid-gus" and p.json()["riot_game_name"] == "Gus"


def test_create_player_unknown_riot_id_is_rejected(client, fake_riot):
    r = client.post("/api/players", json={"display_name": "X", "riot_game_name": "nobody", "riot_tag_line": "1"})
    assert r.status_code == 404 and "not found" in r.json()["detail"]
    assert all(p["display_name"] != "X" for p in client.get("/api/players").json())


def test_create_player_saved_unlinked_when_riot_fails(client, fake_riot):
    fake_riot.error = RiotError(403, "Riot API key rejected")
    p = client.post("/api/players", json={"display_name": "Gus", "riot_game_name": "Gus", "riot_tag_line": "NA1"})
    assert p.status_code == 201
    assert p.json()["puuid"] is None and "rejected" in p.json()["link_error"]


def test_create_player_without_key_does_not_call_riot(client):
    p = client.post("/api/players", json={"display_name": "Gus", "riot_game_name": "Gus", "riot_tag_line": "NA1"})
    assert p.status_code == 201 and p.json()["puuid"] is None and p.json()["link_error"] is None


def test_changing_riot_id_relinks(client, fake_riot):
    fake_riot.accounts[("Gus2", "NA1")] = "puuid-gus2"
    pid = client.post("/api/players", json={"display_name": "Gus", "riot_game_name": "Gus", "riot_tag_line": "NA1"}).json()["id"]
    p = client.patch(f"/api/players/{pid}", json={"riot_game_name": "Gus2"}).json()
    assert p["puuid"] == "puuid-gus2"


def test_bad_region_rejected(client):
    r = client.post("/api/players", json={"display_name": "Z", "region": "mars"})
    assert r.status_code == 400


def test_link_endpoint_reports_errors(client, fake_riot):
    r = client.post("/api/players/1/link")  # player 1 has no Riot ID
    assert r.status_code == 400


def test_sync_and_stats(client, fake_riot):
    client.post("/api/players", json={"display_name": "Gus", "riot_game_name": "Gus", "riot_tag_line": "NA1"})
    r = client.post("/api/sync").json()
    assert r == {"players_synced": 1, "new_matches": 1, "errors": [], "games": []}

    status = client.get("/api/riot/status", params={"check": True}).json()
    assert status["key_set"] and status["key_valid"] and status["last_sync_at"]

    rows = client.get("/api/stats/players", params={"challenge_only": False}).json()
    gus = next(s for s in rows if s["detailed_games"] == 1)
    assert gus["games"] == 1 and gus["kda"] == 6.0 and gus["avg_kills"] == 4


def test_riot_status_without_key(client):
    s = client.get("/api/riot/status", params={"check": True}).json()
    assert s["key_set"] is False and s["key_valid"] is None and "RIOT_API_KEY" in s["message"]


def test_sync_without_key_reports_error(client):
    client.patch("/api/players/1", json={"riot_game_name": "A", "riot_tag_line": "B"})
    # no puuid -> nothing to sync, no error
    assert client.post("/api/sync").json()["players_synced"] == 0


def test_review_flow_and_match_summary(client, session):
    from datetime import timedelta

    from app.models import ChallengeGame, Champion
    from app.services import matcher, sync

    for pid in (1, 2):
        p = session.get(Player, pid)
        p.puuid = f"puuid-{pid}"
        session.add(p)
    session.commit()
    run = create_run(client)
    game = client.post(f"/api/runs/{run['id']}/spins", json={"player_ids": [1, 2]}).json()["game"]
    g = session.get(ChallengeGame, game["id"])
    start = int((g.created_at + timedelta(minutes=2)).timestamp() * 1000)
    parts = [P(f"puuid-{a['player_id']}", session.get(Champion, a["options"][0]).key) for a in game["assignments"]]
    sync.store_match(session, make_match("NA1_55", parts, queue_id=450, start_ms=start))
    matcher.run_matcher(session)
    session.commit()

    flagged = client.get(f"/api/games/{game['id']}").json()
    assert flagged["needs_review"] and "Queue 450" in flagged["review_reason"]
    assert flagged["match"]["match_id"] == "NA1_55" and all(p["in_options"] for p in flagged["match"]["players"])

    done = client.post(f"/api/games/{game['id']}/review", json={"action": "accept"}).json()
    assert done["status"] == "won" and done["result_source"] == "auto" and not done["needs_review"]
    assert client.post(f"/api/games/{game['id']}/review", json={"action": "reject"}).status_code == 409


def test_pool_events_log(client):
    run = create_run(client)
    rid = run["id"]
    client.post(f"/api/runs/{rid}/pool/Champ003/eliminate")
    client.post(f"/api/runs/{rid}/pool/Champ003/revive")
    events = client.get(f"/api/runs/{rid}/events").json()
    assert [e["type"] for e in events] == ["manual_revive", "manual_eliminate"]
    assert events[0]["champion_id"] == "Champ003" and not events[0]["undone"]
    assert client.get("/api/runs/999/events").status_code == 404
