"""Live game tracking: Spectator detection, auto picks and the Live Client summary."""

import asyncio
import random
from datetime import timedelta

import httpx
import pytest
from sqlmodel import Session

from app.models import ChallengeGame, LiveGame, Player, utcnow
from app.services import live, rules

PUUIDS = {1: "puuid-alex", 2: "puuid-bea"}


@pytest.fixture
def game(session) -> ChallengeGame:
    for pid, (name, tag) in {1: ("AlexR", "NA1"), 2: ("BeaR", "EUW")}.items():
        p = session.get(Player, pid)
        p.riot_game_name, p.riot_tag_line, p.puuid = name, tag, PUUIDS[pid]
        session.add(p)
    run = rules.create_run(session, "Live run", 3, group_id=1)
    g = rules.create_spin(session, run, [1, 2], random.Random(3))
    session.commit()
    return g


def options(session, game, pid):
    return next(a.options for a in rules.assignments_for(session, game.id) if a.player_id == pid)


def key(cid: str) -> int:
    return 1000 + int(cid.removeprefix("Champ"))


def spectator(session, game, champs: dict[int, str], split=False, extra_team=100):
    """A Spectator-V5 response with our two players plus strangers."""
    parts = [
        {"puuid": PUUIDS[pid], "championId": key(cid), "teamId": 200 if split and pid == 2 else extra_team,
         "spell1Id": 4, "spell2Id": 14, "perks": {"perkIds": [8112, 8139]}}
        for pid, cid in champs.items()
    ]
    parts += [{"puuid": f"stranger{i}", "championId": 1019 - i, "teamId": 200, "spell1Id": 4, "spell2Id": 12, "perks": {"perkIds": [8010]}} for i in range(3)]
    return {
        "gameId": 5550001, "platformId": "NA1", "gameQueueConfigId": 420, "gameStartTime": 1_760_000_000_000,
        "participants": parts, "bannedChampions": [{"championId": 1015, "teamId": 100}, {"championId": -1, "teamId": 200}],
    }


def test_spectator_fills_picks_and_records_the_game(session, game):
    a, b = options(session, game, 1)[1], options(session, game, 2)[0]
    row = live.apply_spectator(session, game, spectator(session, game, {1: a, 2: b}))
    assert row.riot_game_id == 5550001 and row.platform == "NA1" and row.our_team == 100
    assert row.bans == [{"champion_id": "Champ015", "team": 100}]
    assert {p["player_id"] for p in row.participants} == {1, 2, None}
    picks = {x.player_id: (x.played_champion_id, x.played_option_index) for x in rules.assignments_for(session, game.id)}
    assert picks == {1: (a, 1), 2: (b, 0)}


def test_spectator_ignores_games_without_everyone_together(session, game):
    a, b = options(session, game, 1)[0], options(session, game, 2)[0]
    assert live.apply_spectator(session, game, spectator(session, game, {1: a})) is None  # Bea isn't in it
    assert live.apply_spectator(session, game, spectator(session, game, {1: a, 2: b}, split=True)) is None
    assert session.get(LiveGame, game.id) is None


def test_hand_picks_are_kept(session, game):
    mine = options(session, game, 1)
    rules.set_played(session, game, [rules.Pick(player_id=1, option_index=2)])
    row = live.apply_spectator(session, game, spectator(session, game, {1: mine[0], 2: options(session, game, 2)[0]}))
    assert next(a for a in rules.assignments_for(session, game.id) if a.player_id == 1).played_option_index == 2
    assert "is marked" in row.state["notes"][0]


class FakeRiot:
    def __init__(self, responses):
        self.responses, self.calls = list(responses), 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        pass

    async def active_game(self, platform, puuid):
        self.calls += 1
        return self.responses.pop(0) if self.responses else None


def test_check_spectator_finds_then_ends(session, game):
    data = spectator(session, game, {1: options(session, game, 1)[0], 2: options(session, game, 2)[0]})
    client = FakeRiot([None, data, data, None])
    assert asyncio.run(live.check_spectator(session, client, game)) is None  # still in champ select
    row = asyncio.run(live.check_spectator(session, client, game))
    assert row.riot_game_id == 5550001 and row.ended_at is None
    asyncio.run(live.check_spectator(session, client, game))
    row = asyncio.run(live.check_spectator(session, client, game))
    assert row.ended_at is not None


# --- Live Client Data API ---


def client_player(name, tag, cid, team, position="MIDDLE", items=(), kills=0, deaths=0, assists=0, cs=0, dead=False, level=6):
    return {
        "riotIdGameName": name, "riotIdTagLine": tag, "riotId": f"{name}#{tag}", "summonerName": name,
        "rawChampionName": f"game_character_displayname_{cid}", "championName": cid,
        "team": team, "position": position, "level": level, "isDead": dead, "respawnTimer": 12.4 if dead else 0,
        "items": [{"itemID": i, "price": p, "count": 1, "slot": n, "displayName": f"Item {i}"} for n, (i, p) in enumerate(items)],
        "scores": {"kills": kills, "deaths": deaths, "assists": assists, "creepScore": cs, "wardScore": 7.6},
        "summonerSpells": {
            "summonerSpellOne": {"displayName": "Flash", "rawDisplayName": "GeneratedTip_SummonerSpell_SummonerFlash_DisplayName"},
            "summonerSpellTwo": {"displayName": "Ignite", "rawDisplayName": "GeneratedTip_SummonerSpell_SummonerDot_DisplayName"},
        },
        "runes": {"keystone": {"id": 8112, "displayName": "Electrocute"}},
    }


def client_data(session, game, t=600.0, events=()):
    a, b = options(session, game, 1)[0], options(session, game, 2)[2]
    return {
        "gameData": {"gameTime": t, "gameMode": "CLASSIC"},
        "allPlayers": [
            client_player("AlexR", "NA1", a, "ORDER", "MIDDLE", [(3089, 3600), (3020, 1100)], kills=5, deaths=1, cs=90),
            client_player("BeaR", "EUW", b, "ORDER", "UTILITY", [(3190, 2200)], assists=7, cs=12),
            client_player("Foe1", "KR1", "Champ019", "CHAOS", "MIDDLE", [(3157, 3250)], kills=1, deaths=5, cs=80, dead=True),
            client_player("Foe2", "KR1", "Champ018", "CHAOS", "UTILITY", [], cs=10),
        ],
        "events": {"Events": list(events)},
    }


EVENTS = [
    {"EventName": "GameStart", "EventTime": 0.0},
    {"EventName": "FirstBlood", "EventTime": 190.0, "Recipient": "AlexR"},
    {"EventName": "ChampionKill", "EventTime": 190.0, "KillerName": "AlexR", "VictimName": "Foe1", "Assisters": ["BeaR"]},
    {"EventName": "DragonKill", "EventTime": 300.0, "KillerName": "BeaR", "DragonType": "Fire", "Stolen": "False"},
    {"EventName": "TurretKilled", "EventTime": 420.0, "KillerName": "Minion_T1L1S12N0141", "TurretKilled": "Turret_T2_C_05_A"},
    {"EventName": "HordeKill", "EventTime": 450.0, "KillerName": "Foe2"},
    {"EventName": "Multikill", "EventTime": 500.0, "KillerName": "AlexR", "KillStreak": 2},
]


def test_client_summary(session, game):
    row = live.apply_client(session, game, client_data(session, game, events=EVENTS), static={"items": {3089: {"name": "Rabadon's", "total": 3500}}})
    st = row.state
    assert st["our_team"] == 100 and st["game_time"] == 600
    blue, red = st["teams"]["100"], st["teams"]["200"]
    assert (blue["kills"], red["kills"]) == (5, 1)
    assert blue["gold"] == 3500 + 1100 + 2200  # Data Dragon price wins over the client's
    assert blue["dragons"] == ["Fire"] and blue["towers"] == 1 and red["grubs"] == 1
    alex = next(p for p in st["players"] if p["player_id"] == 1)
    assert alex["option_index"] == 0 and alex["spells"][0]["name"] == "Flash" and alex["kills"] == 5
    bea = next(p for p in st["players"] if p["player_id"] == 2)
    assert bea["option_index"] == 2
    foe = next(p for p in st["players"] if p["champion_id"] == "Champ019")
    assert foe["dead"] and foe["respawn"] == 12 and foe["player_id"] is None
    # Nobody's in-game name is stored: opponents are their champion, ours are their player id.
    assert "Foe1" not in str(st) and "AlexR" not in str(st)
    kill = next(e for e in st["events"] if e["type"] == "kill")
    assert kill["killer"]["player_id"] == 1 and kill["victim"] == {"champion_id": "Champ019", "player_id": None}
    assert [e["type"] for e in st["events"]][:3] == ["multikill", "grubs", "tower"]  # newest first
    assert st["events"][-1]["type"] == "first_blood" and st["events"][-1]["team"] == 100
    # picks were filled in from the client too
    assert {a.player_id: a.played_option_index for a in rules.assignments_for(session, game.id)} == {1: 0, 2: 2}


def test_client_gold_history_samples(session, game):
    live.apply_client(session, game, client_data(session, game, t=60))
    live.apply_client(session, game, client_data(session, game, t=75))  # too soon for a new point
    row = live.apply_client(session, game, client_data(session, game, t=95))
    assert [h["t"] for h in row.state["gold_history"]] == [60, 95]
    assert row.state["gold_history"][-1]["diff"] == (3600 + 1100 + 2200) - 3250


def test_client_game_without_our_players_is_ignored(session, game):
    data = client_data(session, game)
    data["allPlayers"] = data["allPlayers"][2:]
    assert live.apply_client(session, game, data) is None


def test_game_end_marks_ended(session, game):
    row = live.apply_client(session, game, client_data(session, game, events=[{"EventName": "GameEnd", "EventTime": 900.0, "Result": "Win"}]))
    assert row.state["result"] == "Win" and row.ended_at is not None


def test_fetch_live_client(monkeypatch):
    def handler(request):
        assert request.url.path == "/liveclientdata/allgamedata"
        return httpx.Response(200, json={"allPlayers": [{"riotId": "x#y"}]})

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    assert asyncio.run(live.fetch_live_client(http))["allPlayers"]

    down = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(404)))
    assert asyncio.run(live.fetch_live_client(down)) is None

    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "live_client_url", "off")
    assert asyncio.run(live.fetch_live_client(http)) is None


# --- the background job ---


def test_tick_reads_client_and_spaces_out_spectator(engine, session, game, monkeypatch):
    from app.config import get_settings
    from app.jobs import live_tracker

    monkeypatch.setattr(get_settings(), "riot_api_key", "test-key")
    live_tracker._searched.clear()
    data = client_data(session, game, events=EVENTS)
    riot = FakeRiot([None, None])

    async def fetch():
        return data

    assert asyncio.run(live_tracker.tick(engine, client_factory=lambda: riot, fetch=fetch)) == game.id
    assert asyncio.run(live_tracker.tick(engine, client_factory=lambda: riot, fetch=fetch)) == game.id
    assert riot.calls == 1  # Spectator is asked every 30s, not every tick
    with Session(engine) as s:
        assert s.get(LiveGame, game.id).state["teams"]["100"]["kills"] == 5

    live_tracker._searched[game.id] = utcnow() - timedelta(seconds=31)
    with Session(engine) as s:
        row = s.get(LiveGame, game.id)
        row.checked_at = None
        s.add(row)
        s.commit()
    asyncio.run(live_tracker.tick(engine, client_factory=lambda: riot, fetch=fetch))
    assert riot.calls == 2


def test_tick_does_nothing_without_a_pending_game(engine, session):
    async def fetch():
        raise AssertionError("shouldn't read the client")

    from app.jobs import live_tracker

    assert asyncio.run(live_tracker.tick(engine, fetch=fetch)) is None


# --- API ---


def test_live_endpoints(client, session, game):
    assert client.get("/api/live").json() == {"game_id": game.id, "live": None}
    live.apply_client(session, game, client_data(session, game, events=EVENTS))
    session.commit()
    out = client.get("/api/live").json()["live"]
    assert out["streaming"] and out["state"]["teams"]["100"]["kills"] == 5
    assert client.get(f"/api/games/{game.id}/live").json()["live"]["game_id"] == game.id
