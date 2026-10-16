"""Gold (SPEC 7.7), rating (7.10) and contracts (7.9)."""

import random
from datetime import timedelta

import pytest
from sqlmodel import select

from app.models import Contract, GoldLedger, InventoryItem, Player, PlayerMatchStats
from app.services import contracts, economy, rating, rules, shop, shop_config, sync
from tests.factories import P, make_match

CFG = shop_config.effective({})


def pms(**kw) -> PlayerMatchStats:
    base = dict(match_id="x", player_id=1, champion_key=1, team_id=100, win=True)
    return PlayerMatchStats(**{**base, **kw})


# --- the formula --------------------------------------------------------------------------


def test_average_game_benchmark():
    # 5/5/7, 15,000 damage, 20 vision = 50 + 14 + 30 + 10
    g = economy.compute_gold(pms(kills=5, deaths=5, assists=7, damage_to_champs=15000, vision_score=20), CFG)
    assert (g["kills"], g["assists"], g["damage"], g["vision"], g["multikills"]) == (50, 14, 30, 10, 0)
    assert g["total"] == 104


def test_good_game_benchmark():
    # 8/4/10, 20,000 damage, 30 vision, one double kill = 80 + 20 + 40 + 15 + 25
    g = economy.compute_gold(
        pms(kills=8, deaths=4, assists=10, damage_to_champs=20000, vision_score=30, double_kills=1), CFG
    )
    assert g["total"] == 180


@pytest.mark.parametrize(("damage", "gold"), [(4999, 0), (5000, 10), (9999, 10), (10000, 20)])
def test_damage_floor_rounding(damage, gold):
    assert economy.compute_gold(pms(damage_to_champs=damage), CFG)["damage"] == gold


@pytest.mark.parametrize(("vision", "gold"), [(9, 0), (10, 5), (29, 10)])
def test_vision_floor_rounding(vision, gold):
    assert economy.compute_gold(pms(vision_score=vision), CFG)["vision"] == gold


def test_support_bonus_only_for_utility():
    support = pms(team_position="UTILITY", damage_to_champs=3000, heals_on_teammates=4000, shields_on_teammates=3000)
    mid = pms(team_position="MIDDLE", damage_to_champs=3000, heals_on_teammates=4000, shields_on_teammates=3000)
    assert economy.compute_gold(support, CFG)["damage"] == 20  # 10,000 counted
    assert economy.compute_gold(support, CFG)["support_bonus"] is True
    assert economy.compute_gold(mid, CFG)["damage"] == 0  # only the 3,000 damage


def test_multikills_stack_by_default():
    # A penta that Riot also reports as a double, triple and quadra
    g = economy.compute_gold(pms(kills=5, double_kills=1, triple_kills=1, quadra_kills=1, penta_kills=1), CFG)
    assert g["multikills"] == 25 + 50 + 75 + 100
    assert g["kills"] == 50  # on top of 10 per kill


def test_multikills_highest_only_mode():
    cfg = shop_config.effective({"gold": {"multikill_mode": "highest"}})
    g = economy.compute_gold(pms(kills=5, double_kills=1, triple_kills=1, quadra_kills=1, penta_kills=1), cfg)
    assert g["multikills"] == 100
    # two separate doubles still count twice
    assert economy.compute_gold(pms(double_kills=2), cfg)["multikills"] == 50


def test_config_overrides_and_validation():
    cfg = shop_config.effective({"prices": {"shield": 900}})
    assert cfg["prices"]["shield"] == 900 and cfg["prices"]["reroll"] == 250
    with pytest.raises(ValueError):
        shop_config.validate_patch({"prices": {"nope": 1}})
    with pytest.raises(ValueError):
        shop_config.validate_patch({"gold": {"damage_step": 0}})
    with pytest.raises(ValueError):
        shop_config.validate_patch({"blacklist_pct": 2})


# --- rating ---------------------------------------------------------------------------------


def test_grade_order_and_at_least():
    assert rating.at_least("S+", "A+") and rating.at_least("A+", "A+")
    assert not rating.at_least("A", "A+") and not rating.at_least(None, "A+")
    assert rating.grade_for(1.0) == "S+" and rating.grade_for(0.0) == "D"


def test_standout_player_grades_higher_than_teammates():
    raw = make_match(
        "NA1_R",
        [P("star", 1, kills=14, deaths=1, assists=10, damage=45000, vision=60), P("meh", 2, kills=1, deaths=9, assists=2, damage=6000, vision=5)],
    )
    grades = rating.grades_for_match(raw)
    assert rating.GRADES.index(grades["star"]) < rating.GRADES.index(grades["meh"])
    assert rating.at_least(grades["star"], "A+")
    assert not rating.at_least(grades["meh"], "B")


def test_average_teammate_lands_mid_scale():
    team = [P(f"p{i}", i, kills=5, deaths=5, assists=7, damage=15000, vision=20) for i in range(5)]
    grades = rating.grades_for_match(make_match("NA1_AVG", team))
    assert grades["p0"] in ("B+", "B", "B-", "A-")


# --- awarding gold and contracts in games ------------------------------------------------------


PUUIDS = {1: "puuid-alex", 2: "puuid-bea"}


@pytest.fixture
def run(session):
    for pid, puuid in PUUIDS.items():
        p = session.get(Player, pid)
        p.puuid = puuid
        session.add(p)
    r = rules.create_run(session, "R", 3)
    session.commit()
    return r


def play(session, run, result="win", *, kills=(5, 5), assists=(7, 7), seed=0, link=True):
    game = rules.create_spin(session, run, [1, 2], random.Random(seed))
    a = rules.assignments_for(session, game.id)
    rules.set_played(session, game, [rules.Pick(x.player_id, option_index=0) for x in a])
    rules.apply_result(session, game, result)
    if link:
        from app.models import Champion

        parts = [
            P(PUUIDS[x.player_id], session.get(Champion, x.options[0]).key, 100, result == "win",
              kills=kills[i], deaths=3, assists=assists[i], damage=15000, vision=20)
            for i, x in enumerate(a)
        ]
        start = int((game.created_at + timedelta(minutes=2)).timestamp() * 1000)
        sync.store_match(session, make_match(f"NA1_{game.id}", parts, start_ms=start))
        game.riot_match_id = f"NA1_{game.id}"
        economy.award_game(session, game)
    session.commit()
    return game


def give(session, run, player_id, amount):
    economy.record(session, run.id, player_id, amount, "manual_adjust")
    session.commit()


def test_gold_awarded_per_player_and_idempotent(session, run):
    game = play(session, run, kills=(5, 10))
    assert economy.balance(session, run.id, 1) == 104
    assert economy.balance(session, run.id, 2) == 154
    economy.award_game(session, game)  # again: no double pay
    assert economy.balance(session, run.id, 1) == 104
    row = session.exec(select(GoldLedger).where(GoldLedger.player_id == 1)).one()
    assert row.reason == "game" and row.breakdown["kills"] == 50 and row.breakdown["grade"]


def test_same_gold_on_a_loss(session, run):
    play(session, run, "loss")
    assert economy.balance(session, run.id, 1) == 104


def test_no_gold_without_riot_data_or_on_void(session, run):
    play(session, run, link=False)
    g = rules.create_spin(session, run, [1, 2], random.Random(5))
    rules.apply_result(session, g, "void")
    assert economy.award_game(session, g) == []
    assert economy.balance(session, run.id, 1) == 0


def test_undo_reverses_gold_and_contract_payout(session, run):
    give(session, run, 1, 100)
    item, contract = shop.purchase(session, run, 1, "contract", random.Random(0))
    contract.goal_type, contract.target = "kills", "8"
    session.commit()
    game = play(session, run, kills=(9, 1))
    assert contract.status == "won"
    assert economy.balance(session, run.id, 1) == 0 + 144 + 300  # 9 kills: 90 + 14 + 30 + 10
    rules.undo_result(session, game)
    session.commit()
    assert economy.balance(session, run.id, 1) == 0
    assert contract.status == "pending" and contract.game_id is None and item.status == "active"


@pytest.mark.parametrize(
    ("goal", "target", "kills", "assists", "result", "won"),
    [
        ("kills", "8", 8, 0, "loss", True),
        ("kills", "8", 7, 0, "win", False),
        ("assists", "15", 0, 15, "loss", True),
        ("assists", "15", 0, 14, "win", False),
        ("win", "win", 0, 0, "win", True),
        ("win", "win", 20, 20, "loss", False),
    ],
)
def test_contract_goals(session, run, goal, target, kills, assists, result, won):
    give(session, run, 1, 100)
    _, contract = shop.purchase(session, run, 1, "contract")
    contract.goal_type, contract.target = goal, target
    session.commit()
    play(session, run, result, kills=(kills, 1), assists=(assists, 1))
    assert contract.status == ("won" if won else "lost")
    payouts = session.exec(select(GoldLedger).where(GoldLedger.reason == "contract_payout")).all()
    assert len(payouts) == (1 if won else 0)


def test_rating_contract(session, run):
    give(session, run, 1, 100)
    _, contract = shop.purchase(session, run, 1, "contract")
    contract.goal_type, contract.target = "rating", "A+"
    session.commit()
    play(session, run, kills=(20, 0), assists=(15, 0))  # carried hard
    assert contract.status == "won"


def test_one_contract_per_game_and_the_second_waits(session, run):
    give(session, run, 1, 200)
    _, first = shop.purchase(session, run, 1, "contract")
    _, second = shop.purchase(session, run, 1, "contract")
    first.goal_type = second.goal_type = "win"
    first.target = second.target = "win"
    session.commit()
    play(session, run, "win", seed=1)
    assert (first.status, second.status) == ("won", "pending")
    play(session, run, "win", seed=2)
    assert second.status == "won"


def test_contract_waits_when_the_player_sits_out(session, run):
    give(session, run, 1, 100)
    _, contract = shop.purchase(session, run, 1, "contract")
    session.commit()
    game = rules.create_spin(session, run, [2, 3], random.Random(3))  # player 1 not in it
    rules.apply_result(session, game, "win")
    economy.award_game(session, game)
    assert contract.status == "pending"


def test_contract_bought_after_the_spin_waits_for_the_next_game(session, run):
    give(session, run, 1, 100)
    game = rules.create_spin(session, run, [1, 2], random.Random(0))
    session.commit()
    _, contract = shop.purchase(session, run, 1, "contract")
    session.commit()
    rules.apply_result(session, game, "win")
    from app.models import Champion

    a = rules.assignments_for(session, game.id)
    parts = [P(PUUIDS[x.player_id], session.get(Champion, x.options[0]).key) for x in a]
    sync.store_match(session, make_match("NA1_LATE", parts))
    game.riot_match_id = "NA1_LATE"
    economy.award_game(session, game)
    assert contract.status == "pending"


def test_void_leaves_contract_unused(session, run):
    give(session, run, 1, 100)
    item, contract = shop.purchase(session, run, 1, "contract")
    session.commit()
    game = rules.create_spin(session, run, [1, 2], random.Random(0))
    rules.apply_result(session, game, "void")
    economy.award_game(session, game)
    assert contract.status == "pending" and item.status == "active"


def test_contract_goal_is_random_and_uses_config(session, run):
    give(session, run, 1, 400)
    seen = set()
    for seed in range(4):
        _, c = shop.purchase(session, run, 1, "contract", random.Random(seed))
        seen.add(c.goal_type)
        assert c.payout == 300
        assert contracts.describe(c)
    assert seen <= set(contracts.GOALS)
    stored = session.exec(select(Contract)).all()
    assert len(stored) == 4 and all(session.get(InventoryItem, c.item_id).price_paid == 100 for c in stored)
