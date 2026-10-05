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
