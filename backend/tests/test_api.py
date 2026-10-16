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
from sqlmodel import select  # noqa: E402

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


def test_champion_stats_endpoint(client):
    run = create_run(client)
    r = client.get("/api/champions/Champ002/stats", params={"run_id": run["id"]})
    assert r.status_code == 200 and r.json()["status"] == "alive" and r.json()["in_run"]
    assert client.get("/api/champions/Nope/stats").status_code == 404


def test_champion_lines_for_pool_cards(client):
    rid = create_run(client)["id"]
    client.post(f"/api/runs/{rid}/players/1/gold/adjust", json={"amount": 500})
    bl = client.post(f"/api/runs/{rid}/players/1/purchase", json={"type": "blacklist"}).json()["item"]
    client.post(f"/api/items/{bl['id']}/use", json={"champion_ids": ["Champ001"]})
    r = client.post(f"/api/runs/{rid}/spins", json={"player_ids": [2, 3]})
    assert r.status_code == 200, r.text
    game = r.json()["game"]
    mine = next(a for a in game["assignments"] if a["player_id"] == 2)
    offered = mine["options"]
    lines = client.get(f"/api/runs/{rid}/champion-lines").json()
    assert all(lines[c]["offered"] == 1 and lines[c]["on_spin"] == [2] for c in offered)
    assert lines["Champ001"]["blacklisted_by"] == [1]  # player 1 didn't spin, so it stays armed

    client.patch(f"/api/games/{game['id']}/assignments", json={"picks": [{"player_id": p, "option_index": 0} for p in (2, 3)]})
    client.post(f"/api/games/{game['id']}/result", json={"result": "win"})
    lines = client.get(f"/api/runs/{rid}/champion-lines").json()
    assert lines[offered[0]] | {"blacklisted_by": []} == {
        "offered": 1, "played": 1, "wins": 1, "losses": 0, "on_spin": [], "blacklisted_by": []
    }
    assert client.get("/api/runs/999/champion-lines").status_code == 404


def _play(client, rid, result, players=(1, 2)):
    game = client.post(f"/api/runs/{rid}/spins", json={"player_ids": list(players)}).json()["game"]
    picks = [{"player_id": a["player_id"], "option_index": 0} for a in game["assignments"]]
    client.patch(f"/api/games/{game['id']}/assignments", json={"picks": picks})
    return client.post(f"/api/games/{game['id']}/result", json={"result": result}).json()


def test_run_recap(client):
    rid = create_run(client)["id"]
    lost = _play(client, rid, "loss")
    _play(client, rid, "win")
    third = _play(client, rid, "win", players=(1, 3))
    r = client.get(f"/api/runs/{rid}/recap").json()
    t = r["totals"]
    assert (t["games"], t["wins"], t["losses"], t["alive"], t["total"]) == (3, 2, 1, 18, 20)
    assert [g["status"] for g in r["timeline"]] == ["lost", "won", "won"]
    by = {p["player_id"]: p for p in r["players"]}
    assert set(by) == {1, 2, 3} and (by[1]["games"], by[1]["wins"], by[1]["eliminations"]) == (3, 2, 1)
    awards = {a["id"]: a for a in r["awards"]}
    assert awards["mvp"]["player_id"] == 1  # 2-1; player 3 is 1-0 but played too few games to count
    assert awards["first"]["champion_id"] in lost["eliminated"]
    assert "reaper" not in awards  # players 1 and 2 each lost one champ: a tie gets no award
    played_by_3 = [a["played_champion_id"] for a in third["assignments"] if a["player_id"] == 3]
    assert by[3]["top_champion"] == played_by_3[0]  # their only game
    assert client.get("/api/runs/999/recap").status_code == 404


def test_player_profile(client):
    rid = create_run(client)["id"]
    lost = _play(client, rid, "loss")
    _play(client, rid, "win")
    prof = client.get("/api/players/1/profile", params={"run_id": rid}).json()
    assert prof["player"]["display_name"] and prof["stats"]["games"] == 2
    assert [g["status"] for g in prof["games"]] == ["won", "lost"]
    assert prof["games"][1]["eliminated"] and not prof["games"][0]["eliminated"]
    mine = next(a for a in lost["assignments"] if a["player_id"] == 1)
    assert prof["games"][1]["champion_id"] == mine["played_champion_id"]
    assert prof["runs"] == [{"run_id": rid, "name": "Run 1", "status": "active", "games": 2, "wins": 1}]
    assert sum(c["games"] for c in prof["champions"]) == 2
    assert client.get("/api/players/1/profile").status_code == 200  # all runs
    assert client.get("/api/players/999/profile").status_code == 404
    assert client.get("/api/players/1/profile", params={"run_id": 999}).status_code == 404


def test_option_facts(client):
    # 6 champions for 2 players x 3 options: every champion is in someone's options every spin.
    rid = create_run(client, champion_ids=[f"Champ00{i}" for i in range(1, 7)])["id"]
    first = _play(client, rid, "win")
    champ = next(a for a in first["assignments"] if a["player_id"] == 1)["played_champion_id"]
    game = client.post(f"/api/runs/{rid}/spins", json={"player_ids": [1, 2]}).json()["game"]
    facts = client.get(f"/api/games/{game['id']}/option-facts").json()
    assert set(facts) == {"1", "2"}
    for a in game["assignments"]:
        assert set(facts[str(a["player_id"])]) == set(a["options"])
    holder = next(str(a["player_id"]) for a in game["assignments"] if champ in a["options"])
    f = facts[holder][champ]
    assert (f["group_games"], f["group_wins"]) == (1, 1)
    assert f["you_games"] == (1 if holder == "1" else 0)
    assert client.get("/api/games/999/option-facts").status_code == 404


# --- gold and shop endpoints (SPEC 11) ---------------------------------------------------------


def test_shop_flow_over_the_api(client):
    run = create_run(client, owner_player_id=1)
    rid = run["id"]
    assert run["owner_player_id"] == 1 and len(run["lobby_code"]) == 6

    shop_ = client.get(f"/api/runs/{rid}/shop").json()
    assert {i["type"] for i in shop_["items"]} == {"reroll", "blacklist", "swap", "shield", "choose", "contract"}
    assert shop_["blacklist_cap"] == 1  # 20 alive

    r = client.post(f"/api/runs/{rid}/players/1/purchase", json={"type": "shield"})
    assert r.status_code == 409  # no gold yet
    client.post(f"/api/runs/{rid}/players/1/gold/adjust", json={"amount": 1000, "note": "test"})
    bought = client.post(f"/api/runs/{rid}/players/1/purchase", json={"type": "shield"}).json()
    assert bought["balance"] == 300 and bought["item"]["status"] == "unused"

    used = client.post(f"/api/items/{bought['item']['id']}/use", json={"champion_id": "Champ004"}).json()
    assert used["status"] == "active"
    pool = client.get(f"/api/runs/{rid}/pool").json()
    shielded = next(e for e in pool if e["champion_id"] == "Champ004")
    assert shielded["shield_item_id"] == used["id"] and shielded["shield_player_id"] == 1
    assert client.get(f"/api/runs/{rid}").json()["shielded_count"] == 1

    gold = client.get(f"/api/runs/{rid}/players/1/gold").json()
    assert (gold["balance"], gold["earned"], gold["spent"]) == (300, 1000, 700)
    assert [r["reason"] for r in gold["ledger"]] == ["purchase", "manual_adjust"]

    contract = client.post(f"/api/runs/{rid}/players/1/purchase", json={"type": "contract"}).json()["item"]
    assert contract["status"] == "active" and contract["contract"]["description"]
    econ = {e["player_id"]: e for e in client.get(f"/api/runs/{rid}/economy").json()}
    assert econ[1]["balance"] == 200 and econ[1]["active_contract"]["status"] == "pending"
    inv = client.get(f"/api/runs/{rid}/players/1/inventory").json()
    assert [i["type"] for i in inv] == ["contract", "shield"]


def test_spin_items_over_the_api_and_game_details(client):
    rid = create_run(client)["id"]
    client.post(f"/api/runs/{rid}/players/1/gold/adjust", json={"amount": 300})
    reroll = client.post(f"/api/runs/{rid}/players/1/purchase", json={"type": "reroll"}).json()["item"]
    game = client.post(f"/api/runs/{rid}/spins", json={"player_ids": [1, 2]}).json()["game"]
    used = client.post(f"/api/items/{reroll['id']}/use", json={"game_id": game["id"]})
    assert used.status_code == 200
    g = client.get(f"/api/games/{game['id']}").json()
    mine = next(a for a in g["assignments"] if a["player_id"] == 1)
    assert mine["options"] != mine["original_options"]
    assert g["items_used"] == [{"player_id": 1, "type": "reroll", "target": used.json()["target"]}]


def test_shop_config_patch(client):
    rid = create_run(client)["id"]
    r = client.patch(f"/api/runs/{rid}/shop-config", json={"prices": {"shield": 900}, "blacklist_pct": 0.1})
    assert r.status_code == 200
    prices = {i["type"]: i["price"] for i in r.json()["items"]}
    assert prices["shield"] == 900 and prices["reroll"] == 250 and r.json()["blacklist_cap"] == 2
    assert client.patch(f"/api/runs/{rid}/shop-config", json={"prices": {"nope": 1}}).status_code == 400


def test_link_match_endpoint_with_cached_match(client, session):
    from datetime import timedelta

    from app.models import ChallengeGame, Champion
    from app.services import sync as sync_svc

    for pid in (1, 2):
        p = session.get(Player, pid)
        p.puuid = f"puuid-{pid}"
        session.add(p)
    session.commit()
    rid = create_run(client)["id"]
    game = client.post(f"/api/runs/{rid}/spins", json={"player_ids": [1, 2]}).json()["game"]
    client.post(f"/api/games/{game['id']}/result", json={"result": "win"})
    g = session.get(ChallengeGame, game["id"])
    start = int((g.created_at + timedelta(minutes=2)).timestamp() * 1000)
    parts = [P(f"puuid-{a['player_id']}", session.get(Champion, a["options"][0]).key, kills=5, assists=7) for a in game["assignments"]]
    sync_svc.store_match(session, make_match("NA1_999", parts, start_ms=start))
    session.commit()

    assert client.post(f"/api/games/{game['id']}/link-match", json={"riot_match_id": "nope"}).status_code == 400
    linked = client.post(f"/api/games/{game['id']}/link-match", json={"riot_match_id": "na1_999"}).json()
    assert linked["riot_match_id"] == "NA1_999" and linked["status"] == "won"
    assert linked["gold"] == {"1": 104, "2": 104} and set(linked["grades"]) == {"1", "2"}


def test_delete_run_removes_everything_and_reselects(client, session):
    from datetime import timedelta

    from app.models import (
        AppSettings, ChallengeGame, Champion, Contract, GoldLedger, InventoryItem, PlayerMatchStats,
        PoolEntry, PoolEvent, ReviveToken, RiotMatch, SpinAssignment,
    )
    from app.services import sync as sync_svc

    keep = create_run(client, name="Keep")["id"]
    doomed = create_run(client, name="Doomed")["id"]
    for pid in (1, 2):
        p = session.get(Player, pid)
        p.puuid = f"puuid-{pid}"
        session.add(p)
    session.commit()

    # Fill the doomed run with one of everything: gold, items, a contract, a shield, games, tokens, a linked match
    client.post(f"/api/runs/{doomed}/players/1/gold/adjust", json={"amount": 5000})
    shield = client.post(f"/api/runs/{doomed}/players/1/purchase", json={"type": "shield"}).json()["item"]
    client.post(f"/api/items/{shield['id']}/use", json={"champion_id": "Champ001"})
    client.post(f"/api/runs/{doomed}/players/1/purchase", json={"type": "contract"})
    for _ in range(3):
        g = client.post(f"/api/runs/{doomed}/spins", json={"player_ids": [1, 2]}).json()["game"]
        client.post(f"/api/games/{g['id']}/result", json={"result": "win"})
    g = client.post(f"/api/runs/{doomed}/spins", json={"player_ids": [1, 2]}).json()["game"]
    client.post(f"/api/games/{g['id']}/result", json={"result": "loss"})
    game = session.get(ChallengeGame, g["id"])
    start = int((game.created_at + timedelta(minutes=2)).timestamp() * 1000)
    parts = [P(f"puuid-{a['player_id']}", session.get(Champion, a["options"][0]).key) for a in g["assignments"]]
    sync_svc.store_match(session, make_match("NA1_DEL", parts, start_ms=start))
    session.commit()
    client.post(f"/api/games/{g['id']}/link-match", json={"riot_match_id": "NA1_DEL"})
    assert client.get("/api/settings").json()["active_run_id"] == doomed

    assert client.delete(f"/api/runs/{doomed}").status_code == 204
    session.expire_all()
    assert client.get(f"/api/runs/{doomed}").status_code == 404
    assert [r["id"] for r in client.get("/api/runs").json()] == [keep]
    assert session.get(AppSettings, 1).active_run_id == keep
    for model in (PoolEntry, PoolEvent, GoldLedger, InventoryItem, ReviveToken, ChallengeGame):
        assert session.exec(select(model).where(model.run_id == doomed)).all() == []
    assert session.exec(select(Contract)).all() == [] and session.exec(select(SpinAssignment)).all() == []
    # the imported match is kept, just unlinked
    assert session.get(RiotMatch, "NA1_DEL") is not None
    assert all(not r.is_challenge and r.challenge_game_id is None for r in session.exec(select(PlayerMatchStats)).all())
    # the other run is untouched
    assert client.get(f"/api/runs/{keep}").json()["alive_count"] == 20
    assert client.delete(f"/api/runs/{doomed}").status_code == 404


@pytest.mark.parametrize(("raw", "expected"), [("off", ""), ("OFF", ""), ("none", ""), (" RGAPI-x ", "RGAPI-x")])
def test_riot_key_can_be_switched_off(raw, expected):
    from app.config import Settings

    assert Settings(riot_api_key=raw).riot_api_key == expected
