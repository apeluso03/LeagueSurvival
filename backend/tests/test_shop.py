"""Shop and items (SPEC 7.8) and how shields interact with results (7.3, 7.6)."""

import random

import pytest
from sqlmodel import select

from app.models import InventoryItem, PoolEntry, PoolEvent
from app.services import economy, rules, shop
from app.services import spin as spin_logic
from app.services.rules import Pick, RuleError


@pytest.fixture
def run(session):
    r = rules.create_run(session, "R", 3, group_id=1)
    session.commit()
    return r


def rich(session, run, *players, gold=5000):
    for pid in players:
        economy.record(session, run.id, pid, gold, "manual_adjust")
    session.commit()


def buy(session, run, pid, kind):
    item, _ = shop.purchase(session, run, pid, kind)
    session.commit()
    return item


def spin(session, run, players=(1, 2, 3), seed=0):
    g = rules.create_spin(session, run, list(players), random.Random(seed))
    session.commit()
    return g


def mine(session, game, pid):
    return next(a for a in rules.assignments_for(session, game.id) if a.player_id == pid)


# --- buying -----------------------------------------------------------------------------


def test_cannot_buy_without_enough_gold(session, run):
    rich(session, run, 1, gold=249)
    with pytest.raises(RuleError) as e:
        shop.purchase(session, run, 1, "reroll")
    assert e.value.status == 409 and "249" in str(e.value)


def test_purchase_charges_the_buyer_only(session, run):
    rich(session, run, 1, 2, gold=1000)
    item = buy(session, run, 1, "shield")
    assert economy.balance(session, run.id, 1) == 300 and economy.balance(session, run.id, 2) == 1000
    assert item.status == "unused" and item.price_paid == 700
    assert economy.totals(session, run.id, 1) == {"balance": 300, "earned": 1000, "spent": 700}


def test_prices_follow_run_config(session, run):
    run.shop_config = {"prices": {"reroll": 10}}
    session.add(run)
    rich(session, run, 1, gold=10)
    assert buy(session, run, 1, "reroll").price_paid == 10


@pytest.mark.parametrize(("alive", "cap"), [(87, 5), (20, 1), (100, 5), (101, 6), (1, 1), (0, 0)])
def test_blacklist_cap(alive, cap):
    assert shop.blacklist_cap(alive, 0.05) == cap


# --- blacklist ----------------------------------------------------------------------------


def test_blacklist_arms_then_applies_to_owners_next_spin_only(session, run):
    rich(session, run, 1)
    bl = buy(session, run, 1, "blacklist")  # 20 alive -> cap 1
    with pytest.raises(RuleError):
        shop.use_item(session, bl, {"champion_ids": ["Champ001", "Champ002"]})  # over the cap
    shop.use_item(session, bl, {"champion_ids": ["Champ001"]})
    assert bl.status == "armed"
    seen_by_others = False
    for seed in range(25):
        g = spin(session, run, seed=seed)
        a1 = mine(session, g, 1)
        if seed == 0:
            assert "Champ001" not in a1.options and bl.status == "used" and bl.used_in_game_id == g.id
        seen_by_others |= any("Champ001" in a.options for a in rules.assignments_for(session, g.id) if a.player_id != 1)
        rules.void_spin(session, g)
        session.commit()
    assert seen_by_others  # still rollable by everyone else


def test_only_one_armed_blacklist(session, run):
    rich(session, run, 1)
    a, b = buy(session, run, 1, "blacklist"), buy(session, run, 1, "blacklist")
    shop.use_item(session, a, {"champion_ids": ["Champ001"]})
    with pytest.raises(RuleError):
        shop.use_item(session, b, {"champion_ids": ["Champ002"]})


def test_draw_with_blacklists_never_overlaps():
    alive = [f"C{i}" for i in range(12)]
    for seed in range(50):
        out = spin_logic.draw(alive, 3, 3, random.Random(seed), [{"C0", "C1"}, set(), set()])
        flat = [c for o in out for c in o]
        assert len(flat) == len(set(flat)) == 9 and not {"C0", "C1"} & set(out[0])


def test_blacklist_shrinks_that_players_list_when_needed():
    out = spin_logic.draw(["A", "B", "C", "D"], 2, 3, random.Random(1), [{"A", "B", "C"}, set()])
    assert out[0] == ["D"] and len(out[1]) == 2


# --- reroll / swap / choose ---------------------------------------------------------------------


def test_reroll_avoids_old_and_other_players_options(session, run):
    rich(session, run, 1)
    g = spin(session, run)
    before = list(mine(session, g, 1).options)
    others = {c for a in rules.assignments_for(session, g.id) if a.player_id != 1 for c in a.options}
    item = buy(session, run, 1, "reroll")
    shop.use_item(session, item, {"game_id": g.id})
    after = mine(session, g, 1)
    assert len(after.options) == 3 and not set(after.options) & (set(before) | others)
    assert after.original_options == before and item.status == "used" and item.used_in_game_id == g.id
    # more than one reroll on the same spin is fine
    shop.use_item(session, buy(session, run, 1, "reroll"), {"game_id": g.id})


def test_swap_trades_full_lists(session, run):
    rich(session, run, 1)
    g = spin(session, run)
    l1, l2 = list(mine(session, g, 1).options), list(mine(session, g, 2).options)
    shop.use_item(session, buy(session, run, 1, "swap"), {"game_id": g.id, "other_player_id": 2})
    assert mine(session, g, 1).options == l2 and mine(session, g, 2).options == l1
    assert session.exec(select(InventoryItem).where(InventoryItem.player_id == 2)).all() == []  # only the user spends


def test_choose_a_champ(session, run):
    rich(session, run, 1)
    g = spin(session, run)
    on_other = mine(session, g, 2).options[0]
    free = next(c for c in rules.alive_champion_ids(session, run.id)
                if all(c not in a.options for a in rules.assignments_for(session, g.id)))
    item = buy(session, run, 1, "choose")
    with pytest.raises(RuleError):
        shop.use_item(session, item, {"game_id": g.id, "champion_id": on_other})
    shop.use_item(session, item, {"game_id": g.id, "champion_id": free})
    assert mine(session, g, 1).options == [free]


def test_spin_items_respect_their_timing_and_owner(session, run):
    rich(session, run, 1, 4)
    g = spin(session, run)
    # not in this spin
    with pytest.raises(RuleError):
        shop.use_item(session, buy(session, run, 4, "reroll"), {"game_id": g.id})
    # after the champion played is recorded
    rules.set_played(session, g, [Pick(1, option_index=0)])
    with pytest.raises(RuleError):
        shop.use_item(session, buy(session, run, 1, "reroll"), {"game_id": g.id})
    # after the game is over
    rules.apply_result(session, g, "win")
    with pytest.raises(RuleError):
        shop.use_item(session, buy(session, run, 1, "choose"), {"game_id": g.id, "champion_id": "Champ019"})


def test_used_item_cannot_be_used_again(session, run):
    rich(session, run, 1)
    g = spin(session, run)
    item = buy(session, run, 1, "reroll")
    shop.use_item(session, item, {"game_id": g.id})
    with pytest.raises(RuleError):
        shop.use_item(session, item, {"game_id": g.id})


def test_matcher_accepts_champion_from_an_item(session, run):
    """The matcher checks the final list, so a champion picked with Choose a Champ is valid."""
    rich(session, run, 1)
    g = spin(session, run, players=(1, 2))
    free = next(c for c in rules.alive_champion_ids(session, run.id)
                if all(c not in a.options for a in rules.assignments_for(session, g.id)))
    shop.use_item(session, buy(session, run, 1, "choose"), {"game_id": g.id, "champion_id": free})
    assert free in mine(session, g, 1).options and free not in mine(session, g, 1).original_options


# --- shields --------------------------------------------------------------------------------


def place_shield(session, run, pid, champion_id):
    item = buy(session, run, pid, "shield")
    shop.use_item(session, item, {"champion_id": champion_id})
    session.commit()
    return item


def lose_with(session, run, champ_for_p1, seed=0):
    """Spin, make player 1 play `champ_for_p1` (via 'other'), and lose."""
    g = spin(session, run, players=(1, 2), seed=seed)
    picks = [Pick(1, champion_id=champ_for_p1), Pick(2, option_index=0)]
    if champ_for_p1 in mine(session, g, 2).options:
        picks[1] = Pick(2, option_index=mine(session, g, 2).options.index(champ_for_p1) ^ 1)
    rules.set_played(session, g, picks)
    rules.apply_result(session, g, "loss")
    session.commit()
    return g


def test_shield_blocks_exactly_one_elimination(session, run):
    rich(session, run, 1, 3)
    shield = place_shield(session, run, 3, "Champ010")  # any player can shield any champion
    entry = session.get(PoolEntry, (run.id, "Champ010"))
    assert entry.shield_item_id == shield.id and shield.status == "active"

    lose_with(session, run, "Champ010", seed=1)
    assert entry.status == "alive" and entry.shield_item_id is None and shield.status == "used"
    types = [e.type for e in session.exec(select(PoolEvent).order_by(PoolEvent.id)).all()]
    assert types.count("shield_placed") == 1 and types.count("shield_consumed") == 1

    lose_with(session, run, "Champ010", seed=2)  # no shield the second time
    assert entry.status == "eliminated"


def test_one_shield_per_champion_and_only_alive(session, run):
    rich(session, run, 1)
    place_shield(session, run, 1, "Champ010")
    with pytest.raises(RuleError):
        place_shield(session, run, 1, "Champ010")
    rules.manual_eliminate(session, run, "Champ011")
    with pytest.raises(RuleError):
        place_shield(session, run, 1, "Champ011")


def test_manual_elimination_ignores_shields(session, run):
    rich(session, run, 1)
    place_shield(session, run, 1, "Champ010")
    rules.manual_eliminate(session, run, "Champ010")
    assert session.get(PoolEntry, (run.id, "Champ010")).status == "eliminated"


def test_undo_restores_a_consumed_shield(session, run):
    rich(session, run, 1)
    shield = place_shield(session, run, 1, "Champ010")
    g = lose_with(session, run, "Champ010", seed=1)
    rules.undo_result(session, g)
    session.commit()
    entry = session.get(PoolEntry, (run.id, "Champ010"))
    assert entry.shield_item_id == shield.id and shield.status == "active" and shield.used_in_game_id is None


def test_undo_does_not_refund_purchases(session, run):
    rich(session, run, 1, gold=1000)
    g = spin(session, run)
    shop.use_item(session, buy(session, run, 1, "reroll"), {"game_id": g.id})
    rules.apply_result(session, g, "win")
    rules.undo_result(session, g)
    assert economy.balance(session, run.id, 1) == 750


def test_items_belong_to_one_run(session, run):
    rich(session, run, 1)
    item = buy(session, run, 1, "reroll")
    rules.end_run(session, run)
    other = rules.create_run(session, "Next", 3, group_id=1)
    session.commit()
    assert economy.balance(session, other.id, 1) == 0
    g = spin(session, other)
    with pytest.raises(RuleError):
        shop.use_item(session, item, {"game_id": g.id})


def test_gold_adjust_is_logged(session, run):
    shop.adjust_gold(session, run, 2, -40, "oops")
    row = economy.ledger(session, run.id, 2)[0]
    assert (row.amount, row.reason, row.breakdown["note"]) == (-40, "manual_adjust", "oops")
    with pytest.raises(RuleError):
        shop.adjust_gold(session, run, 2, 0, None)
