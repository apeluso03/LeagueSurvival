import asyncio

import pytest
from sqlmodel import select

from app.models import AppSettings, Player, PlayerMatchStats, RiotMatch
from app.services import sync
from app.services.riot_client import RiotError
from tests.factories import FakeRiotClient, P, make_match


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def linked(session):
    """Players 1 and 2 linked to Riot accounts; the rest unlinked."""
    for pid, puuid in ((1, "puuid-alex"), (2, "puuid-bea")):
        p = session.get(Player, pid)
        p.puuid = puuid
        session.add(p)
    session.commit()


def stats_rows(session):
    return session.exec(select(PlayerMatchStats).order_by(PlayerMatchStats.match_id, PlayerMatchStats.player_id)).all()


def test_parse_match():
    raw = make_match("NA1_1", [P("a", 62, early_surrender=False)], queue_id=420, duration=1500)
    m = sync.parse_match(raw)
    assert (m.match_id, m.queue_id, m.game_duration, m.early_surrender) == ("NA1_1", 420, 1500, False)
    assert m.game_start.year >= 2025 and m.game_start.tzinfo is not None


def test_parse_old_match_duration_in_ms():
    raw = make_match("NA1_1", [P("a", 1)], duration=1800)
    del raw["info"]["gameEndTimestamp"]
    raw["info"]["gameDuration"] = 1_800_000
    assert sync.parse_match(raw).game_duration == 1800


def test_parse_early_surrender():
    raw = make_match("NA1_1", [P("a", 1, early_surrender=True)], duration=200)
    assert sync.parse_match(raw).early_surrender is True


def test_store_match_only_tracks_registered_players(session, linked):
    raw = make_match(
        "NA1_1",
        [
            P("puuid-alex", 62, kills=5, deaths=2, assists=7, cs=180, jungle_cs=20),
            P("puuid-bea", 103, kills=3, deaths=4, assists=10),
        ],
    )
    sync.store_match(session, raw)
    rows = stats_rows(session)
    assert [(r.player_id, r.champion_key) for r in rows] == [(1, 62), (2, 103)]
    alex = rows[0]
    assert (alex.kills, alex.deaths, alex.assists, alex.cs) == (5, 2, 7, 200)
    # team kills: alex 5 + bea 3 + 3 strangers x 1
    assert alex.team_kills == 11
    assert alex.is_challenge is False and alex.queue_id == 400


def test_store_match_is_idempotent(session, linked):
    raw = make_match("NA1_1", [P("puuid-alex", 62)])
    sync.store_match(session, raw)
    sync.store_match(session, raw)
    assert len(stats_rows(session)) == 1


def test_link_player_sets_puuid_and_riot_capitalisation(session):
    p = session.get(Player, 3)
    p.riot_game_name, p.riot_tag_line = "cal", "euw"
    client = FakeRiotClient(accounts={("Cal", "EUW"): "puuid-cal"})
    run(sync.link_player(session, client, p))
    assert (p.puuid, p.riot_game_name, p.riot_tag_line) == ("puuid-cal", "Cal", "EUW")


def test_link_player_not_found(session):
    p = session.get(Player, 3)
    p.riot_game_name, p.riot_tag_line = "nobody", "000"
    with pytest.raises(RiotError) as e:
        run(sync.link_player(session, FakeRiotClient(), p))
    assert e.value.status == 404


def test_import_skips_matches_already_cached(session, linked):
    m1 = make_match("NA1_1", [P("puuid-alex", 62), P("puuid-bea", 103)])
    m2 = make_match("NA1_2", [P("puuid-alex", 64)])
    client = FakeRiotClient(matches={"NA1_1": m1, "NA1_2": m2})
    alex, bea = session.get(Player, 1), session.get(Player, 2)

    assert run(sync.import_player_matches(session, client, alex)) == 2
    # Bea's only match was already fetched through Alex: no new fetch, but her row exists
    fetched_before = [c for c in client.calls if c[0] == "match"]
    assert run(sync.import_player_matches(session, client, bea)) == 0
    assert [c for c in client.calls if c[0] == "match"] == fetched_before
    assert {(r.match_id, r.player_id) for r in stats_rows(session)} == {("NA1_1", 1), ("NA1_1", 2), ("NA1_2", 1)}


def test_late_linked_player_gets_rows_from_cached_matches(session, linked):
    m1 = make_match("NA1_1", [P("puuid-alex", 62), P("puuid-cal", 1)])
    client = FakeRiotClient(matches={"NA1_1": m1})
    run(sync.import_player_matches(session, client, session.get(Player, 1)))
    cal = session.get(Player, 3)
    cal.puuid = "puuid-cal"
    session.add(cal)
    run(sync.import_player_matches(session, client, cal))
    assert session.get(PlayerMatchStats, ("NA1_1", 3)) is not None


def test_sync_all_records_time_and_errors(session, linked):
    client = FakeRiotClient(matches={"NA1_1": make_match("NA1_1", [P("puuid-alex", 62)])})
    result = run(sync.sync_all(session, client))
    assert (result.players_synced, result.new_matches, result.errors) == (2, 1, [])
    s = session.get(AppSettings, 1)
    assert s.last_sync_at is not None and s.last_sync_error is None
    assert session.get(RiotMatch, "NA1_1") is not None


def test_sync_all_stops_on_bad_key(session, linked):
    client = FakeRiotClient(error=RiotError(403, "Riot API key rejected"))
    result = run(sync.sync_all(session, client))
    assert result.players_synced == 0
    assert len(result.errors) == 1  # stopped after the first failure
    assert "rejected" in session.get(AppSettings, 1).last_sync_error
