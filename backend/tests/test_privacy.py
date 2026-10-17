"""Keeping little Riot data about people, and deleting it on request (services/privacy.py)."""

from sqlmodel import select

from app.models import MetaChampRole, MetaCrawlState, Player, PlayerMatchStats, RiotMatch
from app.services import privacy, sync
from tests.conftest import make_user
from tests.factories import P, make_match


def link(session, pid, puuid):
    p = session.get(Player, pid)
    p.puuid, p.riot_game_name, p.riot_tag_line = puuid, f"Name{pid}", "NA1"
    session.add(p)
    session.commit()


def named(raw):
    """Give every participant identifying fields, like a real Match-V5 response."""
    for i, p in enumerate(raw["info"]["participants"]):
        p.update(riotIdGameName=f"gamer{i}", riotIdTagline="EUW", summonerName=f"gamer{i}", summonerId=f"s{i}", profileIcon=7)
    return raw


def test_stored_matches_only_identify_registered_players(session):
    link(session, 1, "puuid-1")
    raw = named(make_match("NA1_1", [P("puuid-1", 1000)]))
    sync.store_match(session, raw)
    stored = session.get(RiotMatch, "NA1_1").raw_json
    parts = stored["info"]["participants"]
    assert [p.get("puuid") for p in parts if p.get("puuid")] == ["puuid-1"]
    assert not any(k in p for p in parts for k in ("riotIdGameName", "summonerName", "summonerId", "profileIcon"))
    assert "participants" not in stored["metadata"]
    assert all("kills" in p for p in parts)  # game numbers stay (grades and team stats need them)
    assert session.get(PlayerMatchStats, ("NA1_1", 1)) is not None


def test_scrub_stored_matches_cleans_old_data(session):
    link(session, 1, "puuid-1")
    raw = named(make_match("NA1_2", [P("puuid-1", 1000)]))
    session.add(RiotMatch(match_id="NA1_2", queue_id=400, raw_json=raw))
    session.commit()
    assert privacy.scrub_stored_matches(session) == 1
    assert privacy.scrub_stored_matches(session) == 0
    assert "gamer3" not in str(session.get(RiotMatch, "NA1_2").raw_json)


def test_forget_player(session):
    link(session, 1, "puuid-1")
    link(session, 2, "puuid-2")
    sync.store_match(session, make_match("NA1_3", [P("puuid-1", 1000), P("puuid-2", 1001)]))
    sync.store_match(session, make_match("NA1_4", [P("puuid-1", 1000)]))
    session.commit()

    privacy.forget_player(session, session.get(Player, 1))
    session.commit()
    p = session.get(Player, 1)
    assert (p.puuid, p.riot_game_name, p.riot_tag_line) == (None, None, None)
    assert session.exec(select(PlayerMatchStats).where(PlayerMatchStats.player_id == 1)).all() == []
    assert session.get(RiotMatch, "NA1_4") is None  # only Alex was in it
    assert "puuid-1" not in str(session.get(RiotMatch, "NA1_3").raw_json)  # Bea's stays
    assert session.get(PlayerMatchStats, ("NA1_3", 2)) is not None


def test_forget_puuids_from_a_riot_deletion_list(session):
    link(session, 1, "puuid-1")
    session.add(MetaCrawlState(id=1, puuids=["x", "gone", "y", "z"], next_index=2))
    session.commit()
    out = privacy.forget_puuids(session, ["puuid-1", "gone", " "])
    session.commit()
    assert out == {"requested": 2, "players_forgotten": 1}
    state = session.get(MetaCrawlState, 1)
    assert state.puuids == ["x", "y", "z"] and state.next_index == 1  # still points at "y"


def test_purge_all_keeps_the_challenge(session):
    link(session, 1, "puuid-1")
    sync.store_match(session, make_match("NA1_5", [P("puuid-1", 1000)]))
    session.add(MetaChampRole(champion_key=1000, role="TOP", patch="16.20", games=3, wins=2))
    session.commit()
    privacy.purge_all(session)
    session.commit()
    assert session.exec(select(RiotMatch)).all() == []
    assert session.exec(select(MetaChampRole)).all() == []
    assert session.get(Player, 1).puuid is None
    assert session.get(Player, 1).display_name == "Alex"


def test_privacy_endpoints_are_owner_only(client, session, sign_in):
    link(session, 2, "puuid-2")
    bea = sign_in(make_user(session, "bea", player_id=2))
    assert bea.post("/api/privacy/players/2/forget").status_code == 403
    assert bea.post("/api/privacy/forget", json={"puuids": ["puuid-2"]}).status_code == 403
    assert client.post("/api/privacy/purge", json={"confirm": "yes"}).status_code == 400
    assert client.post("/api/privacy/forget", json={"puuids": ["puuid-2"]}).json()["players_forgotten"] == 1
    assert client.post("/api/privacy/players/1/forget").status_code == 200
    assert client.post("/api/privacy/purge", json={"confirm": "DELETE"}).status_code == 200


def test_a_player_linked_later_is_fetched_again(session):
    import asyncio

    from tests.factories import FakeRiotClient

    link(session, 1, "puuid-1")
    raw = make_match("NA1_6", [P("puuid-1", 1000), P("puuid-2", 1001)])
    sync.store_match(session, raw)  # Bea isn't registered yet, so she's scrubbed out
    session.commit()
    link(session, 2, "puuid-2")
    client = FakeRiotClient(matches={"NA1_6": raw})
    asyncio.run(sync.import_player_matches(session, client, session.get(Player, 2)))
    assert ("match", "NA1_6") in [c[:2] for c in client.calls]
    assert session.get(PlayerMatchStats, ("NA1_6", 2)) is not None
