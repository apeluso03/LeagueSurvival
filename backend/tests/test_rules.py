import random

import pytest
from sqlmodel import select

from app.models import ChallengeGame, PoolEntry, PoolEvent, ReviveToken, Run
from app.services import rules
from app.services.rules import Pick, RuleError

PLAYERS = [1, 2, 3]


@pytest.fixture
def run(session):
    r = rules.create_run(session, "Test run", 3)
    session.commit()
    return r


def spin(session, run, players=PLAYERS, seed=0) -> ChallengeGame:
    game = rules.create_spin(session, run, players, random.Random(seed))
    session.commit()
    return game


def play_first_options(session, game):
    rules.set_played(session, game, [Pick(a.player_id, option_index=0) for a in rules.assignments_for(session, game.id)])


def pool_snapshot(session, run_id):
    return {
        e.champion_id: (e.status, e.eliminated_in_game_id, e.eliminated_by_player_id)
        for e in session.exec(select(PoolEntry).where(PoolEntry.run_id == run_id))
    }


def run_counters(run: Run):
    return (run.win_count, run.current_streak, run.best_streak)


def finish(session, run, result, seed=0):
    game = spin(session, run, seed=seed)
    play_first_options(session, game)
    rules.apply_result(session, game, result)
    session.commit()
    return game


# --- results ----------------------------------------------------------------


def test_win_increments_and_removes_nothing(session, run):
    before = pool_snapshot(session, run.id)
    finish(session, run, "win")
    assert run_counters(run) == (1, 1, 1)
    assert pool_snapshot(session, run.id) == before


def test_win_marks_unmarked_players_as_option_1(session, run):
    game = spin(session, run)
    a = rules.assignments_for(session, game.id)
    rules.set_played(session, game, [Pick(a[0].player_id, option_index=2)])
    rules.apply_result(session, game, "win")
    assert (a[0].played_option_index, a[0].played_champion_id) == (2, a[0].options[2])
    for other in a[1:]:
        assert (other.played_option_index, other.played_champion_id) == (0, other.options[0])


def test_undo_win_keeps_auto_marked_picks(session, run):
    # Harmless: the game is pending again and the picks can be changed before re-recording.
    game = spin(session, run)
    rules.apply_result(session, game, "win")
    rules.undo_result(session, game)
    rules.set_played(session, game, [Pick(a.player_id, option_index=1) for a in rules.assignments_for(session, game.id)])
    rules.apply_result(session, game, "loss")
    assert all(a.played_option_index == 1 for a in rules.assignments_for(session, game.id))


def test_tokens_go_only_to_players_in_the_streak_game(session, run):
    finish(session, run, "win", seed=1)  # players 1, 2, 3
    finish(session, run, "win", seed=2)
    game = rules.create_spin(session, run, [1, 2], random.Random(3))  # player 3 sits out
    rules.apply_result(session, game, "win")
    assert sorted(t.player_id for t in tokens(session, run)) == [1, 2]


def test_loss_eliminates_only_played_champions(session, run):
    game = spin(session, run)
    assignments = rules.assignments_for(session, game.id)
    rules.set_played(session, game, [Pick(a.player_id, option_index=1) for a in assignments])
    rules.apply_result(session, game, "loss")
    session.commit()

    played = {a.options[1] for a in assignments}
    backups = {c for a in assignments for i, c in enumerate(a.options) if i != 1}
    snap = pool_snapshot(session, run.id)
    for cid in played:
        assert snap[cid][0] == "eliminated"
        assert snap[cid][1] == game.id
    for cid in backups:
        assert snap[cid][0] == "alive"
    assert len(rules.alive_champion_ids(session, run.id)) == 20 - len(PLAYERS)
    assert run.current_streak == 0


def test_loss_records_who_played(session, run):
    game = finish(session, run, "loss")
    for a in rules.assignments_for(session, game.id):
        entry = session.get(PoolEntry, (run.id, a.played_champion_id))
        assert entry.eliminated_by_player_id == a.player_id


def test_loss_requires_played_champions(session, run):
    game = spin(session, run)
    with pytest.raises(RuleError):
        rules.apply_result(session, game, "loss")


def test_loss_with_other_pick_outside_options(session, run):
    game = spin(session, run)
    assignments = rules.assignments_for(session, game.id)
    all_options = {c for a in assignments for c in a.options}
    outside = next(c for c in rules.alive_champion_ids(session, run.id) if c not in all_options)
    picks = [Pick(assignments[0].player_id, champion_id=outside)]
    picks += [Pick(a.player_id, option_index=0) for a in assignments[1:]]
    rules.set_played(session, game, picks)
    assert assignments[0].played_option_index is None
    rules.apply_result(session, game, "loss")
    assert session.get(PoolEntry, (run.id, outside)).status == "eliminated"


def test_void_changes_nothing(session, run):
    finish(session, run, "win")
    before_pool = pool_snapshot(session, run.id)
    before_run = run_counters(run)
    game = finish(session, run, "void", seed=1)
    assert game.status == "void"
    assert pool_snapshot(session, run.id) == before_pool
    assert run_counters(run) == before_run


def test_streak_resets_on_loss_and_best_is_kept(session, run):
    finish(session, run, "win", seed=1)
    finish(session, run, "win", seed=2)
    finish(session, run, "loss", seed=3)
    assert run_counters(run) == (2, 0, 2)
    finish(session, run, "win", seed=4)
    assert run_counters(run) == (3, 1, 2)


def test_cannot_resolve_twice(session, run):
    game = finish(session, run, "win")
    with pytest.raises(RuleError):
        rules.apply_result(session, game, "loss")


# --- spins -------------------------------------------------------------------


def test_only_one_pending_game(session, run):
    spin(session, run)
    with pytest.raises(RuleError) as e:
        spin(session, run, seed=1)
    assert e.value.status == 409


def test_spin_draws_only_alive(session, run):
    finish(session, run, "loss")
    alive = set(rules.alive_champion_ids(session, run.id))
    for seed in range(20):
        game = spin(session, run, seed=seed)
        for a in rules.assignments_for(session, game.id):
            assert set(a.options) <= alive
        rules.void_spin(session, game)
        session.commit()


def test_spin_blocked_when_pool_too_small(session):
    r = rules.create_run(session, "Tiny", 3, ["Champ000", "Champ001"])
    with pytest.raises(RuleError) as e:
        rules.create_spin(session, r, PLAYERS)
    assert e.value.status == 409


def test_spin_rejects_bad_player_lists(session, run):
    with pytest.raises(RuleError):
        rules.create_spin(session, run, [1])
    with pytest.raises(RuleError):
        rules.create_spin(session, run, [1, 1])
    with pytest.raises(RuleError):
        rules.create_spin(session, run, [1, 999])


def test_void_spin_allows_new_spin(session, run):
    game = spin(session, run)
    rules.void_spin(session, game)
    assert game.void_reason == "re-roll"
    spin(session, run, seed=1)


def test_same_champion_cannot_be_played_twice(session, run):
    game = spin(session, run)
    a = rules.assignments_for(session, game.id)
    with pytest.raises(RuleError):
        rules.set_played(
            session, game, [Pick(a[0].player_id, option_index=0), Pick(a[1].player_id, champion_id=a[0].options[0])]
        )


# --- tokens ------------------------------------------------------------------


def tokens(session, run):
    return session.exec(select(ReviveToken).where(ReviveToken.run_id == run.id)).all()


def test_tokens_earned_every_third_win(session, run):
    for i in range(2):
        finish(session, run, "win", seed=i)
    assert tokens(session, run) == []
    g3 = finish(session, run, "win", seed=3)
    earned = tokens(session, run)
    assert sorted(t.player_id for t in earned) == PLAYERS
    assert all(t.earned_in_game_id == g3.id for t in earned)
    for i in range(3):
        finish(session, run, "win", seed=10 + i)
    assert len(tokens(session, run)) == 2 * len(PLAYERS)  # streak 6
    for i in range(3):
        finish(session, run, "win", seed=20 + i)
    assert len(tokens(session, run)) == 3 * len(PLAYERS)  # streak 9


def test_streak_broken_restarts_token_count(session, run):
    finish(session, run, "win", seed=1)
    finish(session, run, "win", seed=2)
    finish(session, run, "loss", seed=3)
    finish(session, run, "win", seed=4)
    assert tokens(session, run) == []


def test_use_token_revives(session, run):
    for i in range(3):
        finish(session, run, "win", seed=i)
    loss = finish(session, run, "loss", seed=9)
    victim = rules.assignments_for(session, loss.id)[0].played_champion_id
    token = tokens(session, run)[0]
    rules.use_token(session, token, victim)
    assert session.get(PoolEntry, (run.id, victim)).status == "alive"
    assert token.used_at is not None and token.revived_champion_id == victim
    ev = session.exec(select(PoolEvent).where(PoolEvent.type == "revive")).one()
    assert ev.player_id == token.player_id and ev.token_id == token.id
    with pytest.raises(RuleError):
        rules.use_token(session, token, victim)


def test_token_cannot_revive_alive_champion(session, run):
    for i in range(3):
        finish(session, run, "win", seed=i)
    with pytest.raises(RuleError):
        rules.use_token(session, tokens(session, run)[0], rules.alive_champion_ids(session, run.id)[0])


# --- undo --------------------------------------------------------------------


@pytest.mark.parametrize("result", ["win", "loss", "void"])
def test_undo_restores_exact_previous_state(session, run, result):
    finish(session, run, "win", seed=1)
    finish(session, run, "win", seed=2)
    before_pool = pool_snapshot(session, run.id)
    before_run = run_counters(run)
    before_tokens = len(tokens(session, run))

    game = spin(session, run, seed=3)
    play_first_options(session, game)
    rules.apply_result(session, game, result)  # third game: a win here earns tokens
    session.commit()
    rules.undo_result(session, game)
    session.commit()

    assert game.status == "pending"
    assert pool_snapshot(session, run.id) == before_pool
    assert run_counters(run) == before_run
    assert len(tokens(session, run)) == before_tokens
    # and the result can be applied again
    rules.apply_result(session, game, result)


def test_undo_only_latest_game(session, run):
    first = finish(session, run, "win", seed=1)
    finish(session, run, "win", seed=2)
    with pytest.raises(RuleError):
        rules.undo_result(session, first)


def test_undo_blocked_when_earned_token_spent(session, run):
    for i in range(2):
        finish(session, run, "win", seed=i)
    rules.manual_eliminate(session, run, "Champ000")
    g3 = finish(session, run, "win", seed=5)
    rules.use_token(session, tokens(session, run)[0], "Champ000")
    with pytest.raises(RuleError):
        rules.undo_result(session, g3)


# --- runs and manual edits -----------------------------------------------------


def test_manual_eliminate_and_revive_are_logged(session, run):
    rules.manual_eliminate(session, run, "Champ005")
    assert session.get(PoolEntry, (run.id, "Champ005")).status == "eliminated"
    rules.manual_revive(session, run, "Champ005")
    assert session.get(PoolEntry, (run.id, "Champ005")).status == "alive"
    types = [e.type for e in session.exec(select(PoolEvent).order_by(PoolEvent.id))]
    assert types == ["manual_eliminate", "manual_revive"]


def test_custom_subset_run(session):
    r = rules.create_run(session, "Subset", 4, ["Champ001", "Champ002", "Champ003"])
    assert rules.alive_champion_ids(session, r.id) == ["Champ001", "Champ002", "Champ003"]


def test_end_run_voids_pending_and_blocks_changes(session, run):
    game = spin(session, run)
    rules.end_run(session, run)
    assert run.status == "ended" and game.status == "void"
    with pytest.raises(RuleError):
        rules.create_spin(session, run, PLAYERS)
