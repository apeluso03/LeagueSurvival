"""Clearing test data (services/cleanup.py) and numbering games within their run."""

from datetime import timedelta

from sqlmodel import select

from app import cleanup_cli
from app.models import AppSettings, ChallengeGame, DailyPuzzle, DiscordMessage, PlayerMatchStats, PoolEntry, RiotMatch, Run
from app.services import cleanup, rules
from tests.conftest import GROUP


def play(session, run, result: str) -> ChallengeGame:
    game = rules.create_spin(session, run, [1, 2])
    rules.set_played(session, game, [rules.Pick(player_id=1, option_index=0), rules.Pick(player_id=2, option_index=0)])
    rules.apply_result(session, game, result)
    session.commit()
    return game


def make_world(session):
    old = rules.create_run(session, "Shop Test", 3, group_id=GROUP)
    old_game = play(session, old, "win")
    # A Daily puzzle and a linked Riot match on the old run's game.
    session.add(RiotMatch(match_id="M1", queue_id=400))
    session.flush()
    session.add(PlayerMatchStats(match_id="M1", player_id=1, champion_key=1000, team_id=100, win=True, is_challenge=True, challenge_game_id=old_game.id))
    session.add(DailyPuzzle(group_id=GROUP, day="2026-11-01", number=1, match_id="M1", player_id=1, game_id=old_game.id))

    run = rules.create_run(session, "Hardcore", 3, group_id=GROUP)
    settings = session.exec(select(AppSettings).where(AppSettings.group_id == GROUP)).one()
    settings.active_run_id = run.id
    session.add(settings)
    session.commit()
    test_loss = play(session, run, "loss")  # a test game "before the run started"
    test_loss.created_at = run.started_at - timedelta(hours=1)
    lost_champ = rules.assignments_for(session, test_loss.id)[0].played_champion_id
    session.add(test_loss)
    voided = rules.create_spin(session, run, [1, 2])
    rules.apply_result(session, voided, "void", void_reason="re-roll")
    session.add(DiscordMessage(group_id=GROUP, kind="spin", ref_id=voided.id, channel_id="c", message_id="m"))
    session.commit()
    real = [play(session, run, r) for r in ("win", "win")]
    return run, old, test_loss, voided, real, lost_champ


def test_game_numbers_count_finished_games_in_the_run(session):
    run, old, test_loss, voided, real, _ = make_world(session)
    numbers = rules.game_numbers(session, [run.id, old.id])
    assert numbers[test_loss.id] == 1 and numbers[voided.id] == 2  # a void shares the next game's number
    assert [numbers[g.id] for g in real] == [2, 3]
    pending = rules.create_spin(session, run, [1, 2])
    assert rules.game_number(session, pending) == 4


def test_plan_and_apply(session, capsys):
    run, old, test_loss, voided, real, lost_champ = make_world(session)
    assert session.get(PoolEntry, (run.id, lost_champ)).status == "eliminated"
    p = cleanup.plan(session, GROUP)
    assert [r.id for r, _ in p.other_runs] == [old.id]
    assert [g.id for g in p.voided] == [voided.id] and [g.id for g in p.before_start] == [test_loss.id]

    result = cleanup.apply(session, p)
    session.commit()
    assert result == {"runs_deleted": 1, "games_deleted": 2, "kept": []}
    assert session.get(Run, old.id) is None and session.get(ChallengeGame, voided.id) is None
    assert session.get(PoolEntry, (run.id, lost_champ)).status == "alive"  # the test loss's elimination is undone
    assert session.exec(select(DailyPuzzle)).all() == [] and session.exec(select(DiscordMessage)).all() == []
    pms = session.exec(select(PlayerMatchStats)).one()
    assert (pms.is_challenge, pms.challenge_game_id) == (False, None)  # the Riot match stays as plain stats
    run = session.get(Run, run.id)
    assert (run.win_count, run.current_streak, run.best_streak) == (2, 2, 2)
    assert [rules.game_numbers(session, [run.id])[g.id] for g in real] == [1, 2]
    assert cleanup.plan(session, GROUP).empty


def test_cli_only_changes_with_apply(session, engine, monkeypatch, capsys):
    run, old, *_ = make_world(session)
    old_id = old.id
    monkeypatch.setattr(cleanup_cli, "engine", engine)
    assert cleanup_cli.main([]) == 0
    out = capsys.readouterr().out
    assert "delete run" in out and "Nothing was changed" in out
    session.expire_all()
    assert session.get(Run, old_id) is not None
    assert cleanup_cli.main(["--apply"]) == 2  # needs --group
    assert cleanup_cli.main(["--group", str(GROUP), "--apply"]) == 0
    assert "has games 1 to 2" in capsys.readouterr().out
    session.expire_all()
    assert session.get(Run, old_id) is None


def test_games_show_their_run_number(client, session):
    run, *_ = make_world(session)
    games = client.get(f"/api/games?run_id={run.id}").json()
    assert [g["number"] for g in reversed(games)] == [1, 2, 2, 3]
    numbers = client.get("/api/games/numbers").json()
    assert numbers[str(games[0]["id"])] == 3
