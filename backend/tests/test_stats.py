import random

import pytest

from app.models import Player, PlayerMatchStats
from app.services import rules, stats, sync
from app.services.rules import Pick
from app.services.stats import GameRecord, compute
from tests.factories import P, make_match


def detail(k=0, d=0, a=0, team_kills=10, cs=0, dmg=0, vision=0, secs=1800, win=True):
    return PlayerMatchStats(
        match_id="x", player_id=1, champion_key=1, team_id=100, win=win, kills=k, deaths=d, assists=a,
        team_kills=team_kills, cs=cs, damage_to_champs=dmg, vision_score=vision, game_duration=secs,
    )


def test_kda_with_zero_deaths():
    assert stats.kda(5, 0, 3) == 8.0
    assert stats.kda(5, 2, 3) == 4.0


def test_kp_with_zero_team_kills():
    assert stats.kill_participation(0, 0, 0) is None
    assert stats.kill_participation(3, 2, 10) == 0.5


def test_compute_totals_and_rates():
    s = compute(1, [
        GameRecord("Ahri", True, detail(k=4, d=2, a=6, team_kills=20, cs=180, dmg=18000, vision=30, secs=1800)),
        GameRecord("Ahri", False, detail(k=2, d=4, a=2, team_kills=10, cs=120, dmg=12000, vision=30, secs=1800)),
        GameRecord("Lux", True, None),  # manual challenge game without Riot data
    ])
    assert (s.games, s.wins, s.losses) == (3, 2, 1)
    assert s.win_rate == pytest.approx(2 / 3)
    assert s.detailed_games == 2
    assert (s.avg_kills, s.avg_deaths, s.avg_assists) == (3, 3, 4)
    assert s.kda == pytest.approx((6 + 8) / 6)
    assert s.kill_participation == pytest.approx(14 / 30)
    assert s.cs_per_min == pytest.approx(300 / 60)
    assert s.damage_per_min == pytest.approx(30000 / 60)
    assert s.vision_per_min == pytest.approx(60 / 60)


def test_compute_no_games():
    s = compute(1, [])
    assert s.games == 0 and s.win_rate is None and s.kda is None and s.best_champions == []


def test_best_champions_threshold_and_order():
    recs = [
        GameRecord("OneGame", True, detail(k=20)),  # 1 game: below threshold
        GameRecord("Half", True, detail(k=1, d=1)),
        GameRecord("Half", False, detail(k=1, d=1)),
        GameRecord("AllWinsLowKda", True, detail(k=1, d=5)),
        GameRecord("AllWinsLowKda", True, detail(k=1, d=5)),
        GameRecord("AllWinsHighKda", True, detail(k=10, d=1)),
        GameRecord("AllWinsHighKda", True, None),
    ]
    best = compute(1, recs).best_champions
    assert [c.champion_id for c in best] == ["AllWinsHighKda", "AllWinsLowKda", "Half"]
    assert best[0].games == 2 and best[0].wins == 2 and best[0].kda == 10.0
    assert best[2].win_rate == 0.5


# --- database gathering ------------------------------------------------------------


@pytest.fixture
def setup(session):
    for pid, puuid in ((1, "puuid-alex"), (2, "puuid-bea")):
        p = session.get(Player, pid)
        p.puuid = puuid
        session.add(p)
    run = rules.create_run(session, "R", 3)
    session.commit()
    return run


def challenge_game(session, run, result, seed=0):
    game = rules.create_spin(session, run, [1, 2], random.Random(seed))
    rules.set_played(session, game, [Pick(1, option_index=0), Pick(2, option_index=1)])
    rules.apply_result(session, game, result)
    session.commit()
    return game


def test_challenge_only_counts_challenge_games(session, setup):
    challenge_game(session, setup, "win", seed=1)
    challenge_game(session, setup, "loss", seed=2)
    sync.store_match(session, make_match("NA1_9", [P("puuid-alex", 1001, kills=9)]))  # casual

    [alex, bea] = stats.player_stats(session, [1, 2], setup.id, challenge_only=True)
    assert (alex.games, alex.wins, alex.losses) == (2, 1, 1)
    assert alex.detailed_games == 0 and alex.kda is None
    assert len(alex.eliminated_champions) == 1 and len(bea.eliminated_champions) == 1


def test_all_games_includes_casual_and_skips_remakes(session, setup):
    challenge_game(session, setup, "win", seed=1)
    sync.store_match(session, make_match("NA1_9", [P("puuid-alex", 1001, kills=9, win=False)]))
    sync.store_match(session, make_match("NA1_10", [P("puuid-alex", 1002)], duration=200))  # remake by time
    sync.store_match(
        session, make_match("NA1_11", [P("puuid-alex", 1003, early_surrender=True)], duration=900)
    )  # early surrender

    [alex] = stats.player_stats(session, [1], None, challenge_only=False)
    assert (alex.games, alex.wins, alex.losses) == (2, 1, 1)
    assert alex.detailed_games == 1 and alex.avg_kills == 9


def test_challenge_game_uses_linked_riot_stats(session, setup):
    game = challenge_game(session, setup, "win", seed=1)
    sync.store_match(session, make_match("NA1_5", [P("puuid-alex", 1000, kills=7, deaths=1)]))
    game.riot_match_id = "NA1_5"
    pms = session.get(PlayerMatchStats, ("NA1_5", 1))
    pms.is_challenge, pms.challenge_game_id = True, game.id
    session.add_all([game, pms])
    session.commit()

    [alex] = stats.player_stats(session, [1], setup.id, challenge_only=True)
    assert alex.detailed_games == 1 and alex.kda == 7.0
    # And it isn't double counted under "all"
    [alex_all] = stats.player_stats(session, [1], None, challenge_only=False)
    assert alex_all.games == 1


def test_undone_elimination_not_listed(session, setup):
    game = challenge_game(session, setup, "loss", seed=1)
    rules.undo_result(session, game)
    session.commit()
    [alex] = stats.player_stats(session, [1], setup.id)
    assert alex.eliminated_champions == []
