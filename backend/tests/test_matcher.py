import asyncio
import random
from datetime import timedelta

import pytest
from sqlmodel import select

from app.models import AppSettings, ChallengeGame, Champion, Player, PlayerMatchStats, PoolEntry
from app.services import matcher, rules, sync
from tests.factories import FakeRiotClient, P, make_match

PUUIDS = {1: "puuid-alex", 2: "puuid-bea", 3: "puuid-cal"}


@pytest.fixture
def ctx(session):
    for pid, puuid in PUUIDS.items():
        p = session.get(Player, pid)
        p.puuid = puuid
        session.add(p)
    run = rules.create_run(session, "R", 3)
    session.commit()
    return run


def settings(session) -> AppSettings:
    return session.get(AppSettings, 1)


def spin(session, run, players=(1, 2, 3), seed=0) -> ChallengeGame:
    game = rules.create_spin(session, run, list(players), random.Random(seed))
    session.commit()
    return game


def key(session, champion_id: str) -> int:
    return session.get(Champion, champion_id).key


def start_ms(game: ChallengeGame, minutes_after: int = 3) -> int:
    return int((game.created_at + timedelta(minutes=minutes_after)).timestamp() * 1000)


def store_game_match(session, game, match_id="NA1_100", option=0, win=True, team_of=None, champs=None, **kw):
    """Store a match where each player in `game` played options[option] (or `champs[pid]`)."""
    parts = []
    for a in rules.assignments_for(session, game.id):
        cid = (champs or {}).get(a.player_id, a.options[option])
        team = (team_of or {}).get(a.player_id, 100)
        parts.append(P(PUUIDS[a.player_id], key(session, cid), team, win, kills=3, deaths=2, assists=5))
    kw.setdefault("start_ms", start_ms(game))
    sync.store_match(session, make_match(match_id, parts, **kw))
    session.commit()


def run_once(session, game):
    outcome = matcher.match_pending(session, game, settings(session))
    session.commit()
    return outcome


# --- spec cases ----------------------------------------------------------------------


def test_clean_win_applies_automatically(session, ctx):
    game = spin(session, ctx)
    store_game_match(session, game, option=1, win=True)
    outcome = run_once(session, game)
    assert outcome.status == "applied" and outcome.message == "Win"
    assert (game.status, game.result_source, game.riot_match_id) == ("won", "auto", "NA1_100")
    assert all(a.played_option_index == 1 for a in rules.assignments_for(session, game.id))
    assert ctx.win_count == 1
    rows = session.exec(select(PlayerMatchStats).where(PlayerMatchStats.match_id == "NA1_100")).all()
    assert all(r.is_challenge and r.challenge_game_id == game.id for r in rows) and len(rows) == 3


def test_clean_loss_eliminates_played_champions(session, ctx):
    game = spin(session, ctx)
    store_game_match(session, game, option=2, win=False)
    assert run_once(session, game).status == "applied"
    for a in rules.assignments_for(session, game.id):
        assert session.get(PoolEntry, (ctx.id, a.options[2])).status == "eliminated"
        assert session.get(PoolEntry, (ctx.id, a.options[0])).status == "alive"


def test_wrong_champion_needs_review(session, ctx):
    game = spin(session, ctx)
    a0 = rules.assignments_for(session, game.id)[0]
    outside = next(c for c in rules.alive_champion_ids(session, ctx.id)
                   if all(c not in a.options for a in rules.assignments_for(session, game.id)))
    store_game_match(session, game, champs={a0.player_id: outside}, win=False)
    outcome = run_once(session, game)
    assert outcome.status == "needs_review" and "wasn't one of their options" in outcome.message
    assert game.status == "pending" and game.needs_review and game.riot_match_id == "NA1_100"
    assert len(rules.alive_champion_ids(session, ctx.id)) == 20  # nothing eliminated


def test_wrong_queue_needs_review(session, ctx):
    game = spin(session, ctx)
    store_game_match(session, game, queue_id=450)  # ARAM not allowed by default
    outcome = run_once(session, game)
    assert outcome.status == "needs_review" and "Queue 450" in outcome.message
    assert ctx.win_count == 0


def test_players_on_different_teams_needs_review(session, ctx):
    game = spin(session, ctx)
    store_game_match(session, game, team_of={3: 200})
    assert "different teams" in run_once(session, game).message


def test_remake_voids_the_game(session, ctx):
    game = spin(session, ctx)
    store_game_match(session, game, duration=180, win=False)
    outcome = run_once(session, game)
    assert outcome.status == "voided"
    assert (game.status, game.result_source, game.void_reason) == ("void", "auto", "remake")
    assert len(rules.alive_champion_ids(session, ctx.id)) == 20


def test_early_surrender_counts_as_remake(session, ctx):
    game = spin(session, ctx)
    store_game_match(session, game, duration=900, win=False)
    from app.models import RiotMatch
    m = session.get(RiotMatch, "NA1_100")
    m.early_surrender = True
    session.add(m)
    session.commit()
    assert run_once(session, game).status == "voided"


def test_no_match_yet_keeps_waiting(session, ctx):
    game = spin(session, ctx)
    assert run_once(session, game).status == "waiting"
    assert game.status == "pending" and not game.needs_review


# --- candidate selection --------------------------------------------------------------


def test_ignores_matches_before_the_spin(session, ctx):
    game = spin(session, ctx)
    store_game_match(session, game, start_ms=start_ms(game, minutes_after=-30))
    assert run_once(session, game).status == "waiting"


def test_needs_every_player_in_the_match(session, ctx):
    game = spin(session, ctx)
    a = rules.assignments_for(session, game.id)
    parts = [P(PUUIDS[x.player_id], key(session, x.options[0])) for x in a[:2]]  # Cal missing
    sync.store_match(session, make_match("NA1_100", parts, start_ms=start_ms(game)))
    assert run_once(session, game).status == "waiting"


def test_picks_the_earliest_matching_game(session, ctx):
    game = spin(session, ctx)
    store_game_match(session, game, match_id="NA1_LATE", start_ms=start_ms(game, 60), win=False)
    store_game_match(session, game, match_id="NA1_EARLY", start_ms=start_ms(game, 3), win=True)
    assert run_once(session, game).match_id == "NA1_EARLY"


def test_unlinked_player_blocks_auto_results(session, ctx):
    game = spin(session, ctx, players=(1, 4))  # Dee has no Riot account
    outcome = run_once(session, game)
    assert outcome.status == "unlinked" and "Dee" in outcome.message


def test_challenge_mode_off_never_touches_the_pool(session, ctx):
    game = spin(session, ctx)
    store_game_match(session, game, win=False)
    s = settings(session)
    s.challenge_mode = False
    session.add(s)
    session.commit()
    assert run_once(session, game).status == "skipped"
    assert game.status == "pending" and len(rules.alive_champion_ids(session, ctx.id)) == 20


# --- review and undo ---------------------------------------------------------------------


def test_accept_review_applies_with_riot_champions(session, ctx):
    game = spin(session, ctx)
    a0 = rules.assignments_for(session, game.id)[0]
    taken = {c for a in rules.assignments_for(session, game.id) for c in a.options}
    outside = next(c for c in rules.alive_champion_ids(session, ctx.id) if c not in taken)
    store_game_match(session, game, champs={a0.player_id: outside}, win=False)
    run_once(session, game)

    matcher.accept_review(session, game, settings(session))
    session.commit()
    assert (game.status, game.result_source, game.needs_review) == ("lost", "auto", False)
    assert game.riot_match_id == "NA1_100" and game.rejected_match_ids == []
    assert a0.played_champion_id == outside and a0.played_option_index is None
    assert session.get(PoolEntry, (ctx.id, outside)).status == "eliminated"


def test_reject_review_looks_for_another_match(session, ctx):
    game = spin(session, ctx)
    store_game_match(session, game, match_id="NA1_ARAM", queue_id=450, start_ms=start_ms(game, 3))
    run_once(session, game)
    matcher.reject_review(session, game)
    session.commit()
    assert not game.needs_review and game.rejected_match_ids == ["NA1_ARAM"]
    store_game_match(session, game, match_id="NA1_REAL", start_ms=start_ms(game, 40))
    outcome = run_once(session, game)
    assert outcome.status == "applied" and outcome.match_id == "NA1_REAL"


def test_manual_result_on_flagged_game_drops_the_match(session, ctx):
    game = spin(session, ctx)
    store_game_match(session, game, queue_id=450)
    run_once(session, game)
    rules.apply_result(session, game, "win")
    assert game.riot_match_id is None and not game.needs_review and game.rejected_match_ids == ["NA1_100"]


def test_undo_auto_result_sticks(session, ctx):
    game = spin(session, ctx)
    store_game_match(session, game, win=False)
    run_once(session, game)
    rules.undo_result(session, game)
    session.commit()
    assert game.status == "pending" and game.riot_match_id is None
    assert game.rejected_match_ids == ["NA1_100"]
    rows = session.exec(select(PlayerMatchStats).where(PlayerMatchStats.match_id == "NA1_100")).all()
    assert not any(r.is_challenge for r in rows)
    # the next poll doesn't re-apply the undone match
    assert run_once(session, game).status == "waiting"
    assert len(rules.alive_champion_ids(session, ctx.id)) == 20


def test_match_not_reused_for_a_second_game(session, ctx):
    g1 = spin(session, ctx)
    store_game_match(session, g1)
    run_once(session, g1)
    g2 = spin(session, ctx, seed=1)
    # The same match would cover g2's players too, but it's already linked to g1
    assert run_once(session, g2).status == "waiting"


# --- linking hand-recorded games for stats --------------------------------------------------


def test_manual_win_gets_linked_and_champions_corrected(session, ctx):
    game = spin(session, ctx)
    rules.apply_result(session, game, "win")  # everyone assumed option 1
    session.commit()
    store_game_match(session, game, option=2, win=True)
    [outcome] = matcher.run_matcher(session)
    assert outcome.status == "linked"
    assert game.result_source == "manual" and game.riot_match_id == "NA1_100"
    assert all(a.played_option_index == 2 for a in rules.assignments_for(session, game.id))


def test_manual_game_not_linked_when_riot_disagrees(session, ctx):
    game = spin(session, ctx)
    rules.apply_result(session, game, "win")
    session.commit()
    store_game_match(session, game, win=False)
    assert matcher.run_matcher(session) == []
    assert game.riot_match_id is None and game.status == "won"


# --- poller --------------------------------------------------------------------------------


def test_poll_once_imports_and_applies(engine, session, ctx, monkeypatch):
    from app.config import get_settings
    from app.jobs import poller

    game = spin(session, ctx)
    parts = [P(PUUIDS[a.player_id], key(session, a.options[0]), 100, True)
             for a in rules.assignments_for(session, game.id)]
    fake = FakeRiotClient(matches={"NA1_7": make_match("NA1_7", parts, start_ms=start_ms(game))})
    monkeypatch.setattr(get_settings(), "riot_api_key", "RGAPI-test")

    outcomes = asyncio.run(poller.poll_once(engine, client_factory=lambda: fake))
    assert [o.status for o in outcomes] == ["applied"]
    session.expire_all()
    assert session.get(ChallengeGame, game.id).status == "won"


def test_poll_once_idle_without_pending_game(engine, session, ctx, monkeypatch):
    from app.config import get_settings
    from app.jobs import poller

    monkeypatch.setattr(get_settings(), "riot_api_key", "RGAPI-test")
    fake = FakeRiotClient()
    assert asyncio.run(poller.poll_once(engine, client_factory=lambda: fake)) is None
    assert fake.calls == []


def test_poll_once_idle_without_key(engine, session, ctx):
    from app.jobs import poller

    spin(session, ctx)
    fake = FakeRiotClient()
    assert asyncio.run(poller.poll_once(engine, client_factory=lambda: fake)) is None
