import random

import pytest

from app.services.spin import SpinBlocked, draw, effective_options

CHAMPS = [f"C{i}" for i in range(30)]


@pytest.mark.parametrize("players", [2, 3, 4, 5])
@pytest.mark.parametrize("n", [3, 4])
def test_no_duplicates_across_players(players, n):
    for seed in range(50):
        result = draw(CHAMPS, players, n, random.Random(seed))
        flat = [c for opts in result for c in opts]
        assert len(result) == players
        assert all(len(opts) == n for opts in result)
        assert len(flat) == len(set(flat))


def test_only_draws_from_given_alive_ids():
    alive = CHAMPS[:12]
    for seed in range(50):
        flat = [c for opts in draw(alive, 3, 4, random.Random(seed)) for c in opts]
        assert set(flat) <= set(alive)


def test_shrinks_evenly_when_pool_is_small():
    # 7 alive, 3 players, wants 3 each -> 2 each
    result = draw(CHAMPS[:7], 3, 3, random.Random(1))
    assert [len(o) for o in result] == [2, 2, 2]
    # 5 alive, 5 players -> 1 each
    result = draw(CHAMPS[:5], 5, 4, random.Random(1))
    assert [len(o) for o in result] == [1, 1, 1, 1, 1]


def test_blocked_when_fewer_alive_than_players():
    with pytest.raises(SpinBlocked):
        draw(CHAMPS[:2], 3, 3)


def test_effective_options():
    assert effective_options(100, 5, 4) == 4
    assert effective_options(9, 3, 4) == 3
    assert effective_options(2, 3, 3) == 0


@pytest.mark.parametrize("players", [0, 1, 6])
def test_player_count_bounds(players):
    with pytest.raises(ValueError):
        draw(CHAMPS, players, 3)


def test_options_must_be_3_or_4():
    with pytest.raises(ValueError):
        draw(CHAMPS, 2, 5)
