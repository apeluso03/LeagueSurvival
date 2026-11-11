"""The Graveyard (SPEC 21): headstones for eliminated champions, epitaphs and the run's totals."""

from sqlmodel import select

from app.models import PlayerMatchStats, PoolEntry, ReviveToken, RiotMatch
from app.services import graveyard, rules
from tests.conftest import GROUP


def play(session, run, picks: dict[int, int], result: str):
    """Spin for the players in `picks` and record a result with each on option `picks[pid]`."""
    game = rules.create_spin(session, run, list(picks))
    rules.set_played(session, game, [rules.Pick(player_id=pid, option_index=i) for pid, i in picks.items()])
    rules.apply_result(session, game, result)
    session.commit()
    return game


def played(session, game, pid) -> str:
    return next(a for a in rules.assignments_for(session, game.id) if a.player_id == pid).played_champion_id


def test_headstones_records_and_totals(session):
    run = rules.create_run(session, "Run", 3, group_id=GROUP)
    win = play(session, run, {1: 0, 2: 0}, "win")
    survivor = played(session, win, 1)
    loss = play(session, run, {1: 0, 2: 0}, "loss")
    a_dead, b_dead = played(session, loss, 1), played(session, loss, 2)
    # Riot stats for Alex's fatal game: 2/12/1, so the epitaph mentions the deaths (if not first-game).
    session.add(RiotMatch(match_id="M1", queue_id=400, game_duration=1500))
    session.flush()
    session.add(
        PlayerMatchStats(
            match_id="M1", player_id=1, champion_key=1000, team_id=100, win=False, kills=2, deaths=12, assists=1,
            rating_grade="D", game_duration=1500, is_challenge=True, challenge_game_id=loss.id,
        )
    )
    alive = session.exec(select(PoolEntry).where(PoolEntry.run_id == run.id, PoolEntry.status == "alive")).all()
    rules.manual_eliminate(session, run, next(e.champion_id for e in alive if e.champion_id != survivor))
    session.commit()

    g = graveyard.build(session, run)
    assert (g.total, g.dead) == (20, 3)
    stones = {h.champion_id: h for h in g.headstones}
    a = stones[a_dead]
    assert (a.game_id, a.player_id, a.manual, a.games_survived) == (loss.id, 1, False, 1)
    assert (a.last_game.kills, a.last_game.deaths, a.last_game.grade) == (2, 12, "D")
    assert a.played >= 1 and a.losses == 1 and a.deaths == 1
    assert stones[b_dead].last_game is None  # no Riot stats for Bea
    manual = next(h for h in g.headstones if h.manual)
    assert manual.epitaph.startswith("Removed by hand")
    assert g.headstones[0].manual  # newest first
    assert {d["player_id"]: d["count"] for d in g.diggers} == {1: 1, 2: 1}
    assert g.first_blood in (a_dead, b_dead) and g.quickest in (a_dead, b_dead)
    assert g.by_class == [{"tag": "Fighter", "count": 3}]


def test_revived_champions_rise_and_count_deaths(session):
    run = rules.create_run(session, "Run", 3, group_id=GROUP)
    for _ in range(3):
        play(session, run, {1: 0, 2: 0}, "win")  # a 3-win streak earns tokens
    loss = play(session, run, {1: 0, 2: 0}, "loss")
    dead = played(session, loss, 1)
    token = session.exec(select(ReviveToken).where(ReviveToken.run_id == run.id)).first()
    rules.use_token(session, token, dead)
    session.commit()
    g = graveyard.build(session, run)
    assert dead not in {h.champion_id for h in g.headstones}
    assert [(r.champion_id, r.revived, r.deaths) for r in g.risen] == [(dead, 1, 1)]


def test_epitaphs():
    base = dict(
        champion_id="X", name="X", title="", tags=[], image_url="", eliminated_at=None, game_id=7, game_number=3, player_id=1, manual=False,
        last_game=None, offered=2, played=3, wins=0, losses=1, games_survived=4, deaths=1, revived=0, shields_broken=0, epitaph="",
    )
    h = lambda **kw: graveyard.Headstone(**{**base, **kw})  # noqa: E731
    lg = lambda **kw: graveyard.LastGame(**{"kills": 3, "deaths": 3, "assists": 3, "grade": "B", "duration": 1500, "team_position": None, **kw})  # noqa: E731
    assert graveyard.epitaph(h(played=1, offered=5)) == "Offered 5 times. Played once. Gone."
    assert graveyard.epitaph(h(played=1)) == "One game. That's all it got."
    assert graveyard.epitaph(h(last_game=lg(grade="S"))) == "Went down swinging: S in its last game."
    assert graveyard.epitaph(h(last_game=lg(deaths=11))).startswith("Died 11 times")
    assert graveyard.epitaph(h(revived=2)) == "Came back 2 times. Not this time."
    assert graveyard.epitaph(h(wins=4)) == "4 wins before the fall."
    assert graveyard.epitaph(h()) == "Fell in game 3."


def test_api(client, session):
    run = rules.create_run(session, "Run", 3, group_id=GROUP)
    session.commit()
    res = client.get(f"/api/runs/{run.id}/graveyard")
    assert res.status_code == 200
    assert res.json()["dead"] == 0 and res.json()["headstones"] == []
    assert client.get("/api/runs/9999/graveyard").status_code == 404
