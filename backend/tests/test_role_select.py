"""Role Select: lock your role for your next spin (shop item, 400 gold)."""

import random

import pytest
from sqlmodel import select

from app.models import Champion, InventoryItem
from app.services import discord_bot, economy, rules, shop
from app.services.rules import RuleError
from tests.conftest import GROUP
from tests.test_discord import cmd, world  # noqa: F401 - fixture

# 20 champions, four per role. Champ003 is a top laner who also goes mid; Champ014 mains bot but
# also plays support.
ROLES = {
    "TOP": range(0, 4),
    "JUNGLE": range(4, 8),
    "MIDDLE": range(8, 12),
    "BOTTOM": range(12, 16),
    "SUPPORT": range(16, 20),
}
EXTRA = {3: ["MIDDLE"], 14: ["SUPPORT"]}


@pytest.fixture
def run(session):
    for pos, ids in ROLES.items():
        for i in ids:
            c = session.get(Champion, f"Champ{i:03d}")
            c.positions = [pos, *EXTRA.get(i, [])]
            session.add(c)
    r = rules.create_run(session, "Run", 3, group_id=GROUP)
    for pid in (1, 2, 3):
        economy.record(session, r.id, pid, 2000, "manual_adjust")
    session.commit()
    return r


def lock(session, run, pid, role) -> InventoryItem:
    item, _ = shop.purchase(session, run, pid, "role")
    shop.use_item(session, item, {"role": role})
    session.commit()
    return item


def champs(*indexes) -> set[str]:
    return {f"Champ{i:03d}" for i in indexes}


def test_it_costs_400_and_arms_for_the_next_spin(session, run):
    item = lock(session, run, 1, "BOTTOM")
    assert item.price_paid == 400 and item.status == "armed" and item.target == {"role": "BOTTOM"}
    assert economy.balance(session, run.id, 1) == 1600
    assert shop.catalog(session, run)["locked_roles"] == {"BOTTOM": 1}


def test_the_spin_follows_the_locked_role(session, run):
    item = lock(session, run, 1, "BOTTOM")
    for seed in range(20):  # every draw, not just a lucky one
        options = rules.draw_options(
            session, run, [1, 2, 3], random.Random(seed),
            exclude={2: champs(12, 13, 14, 15), 3: champs(12, 13, 14, 15)},
            allowed={1: champs(12, 13, 14, 15)},
        )
        assert set(options[0]) <= champs(12, 13, 14, 15)
        assert not (set(options[1]) | set(options[2])) & champs(12, 13, 14, 15)

    game = rules.create_spin(session, run, [1, 2, 3], random.Random(1))
    alex, bea, cal = rules.assignments_for(session, game.id)
    assert set(alex.options) <= champs(12, 13, 14, 15) and alex.played_role == "BOTTOM"
    assert not (set(bea.options) | set(cal.options)) & champs(12, 13, 14, 15)  # nobody else gets a bot laner
    assert bea.played_role is None
    session.refresh(item)
    assert (item.status, item.used_in_game_id) == ("used", game.id)
    assert shop.catalog(session, run)["locked_roles"] == {}


def test_others_can_still_roll_champions_that_only_play_it_second(session, run):
    lock(session, run, 1, "MIDDLE")
    lock(session, run, 2, "TOP")
    game = rules.create_spin(session, run, [1, 2, 3], random.Random(3))
    alex, bea, cal = rules.assignments_for(session, game.id)
    assert set(alex.options) <= champs(8, 9, 10, 11, 3)  # Champ003 plays mid too
    assert set(bea.options) <= champs(0, 1, 2, 3)
    assert not set(cal.options) & champs(0, 1, 2, 3, 8, 9, 10, 11)  # mains of both locked roles


def test_one_player_per_role(session, run):
    lock(session, run, 1, "JUNGLE")
    item, _ = shop.purchase(session, run, 2, "role")
    with pytest.raises(RuleError, match="already locked Jungle"):
        shop.use_item(session, item, {"role": "JUNGLE"})
    with pytest.raises(RuleError, match="Pick a role"):
        shop.use_item(session, item, {"role": "ADC"})
    item2, _ = shop.purchase(session, run, 1, "role")
    with pytest.raises(RuleError, match="already has Jungle locked"):
        shop.use_item(session, item2, {"role": "MIDDLE"})


def test_a_role_with_no_champions_left(session, run):
    for i in [*ROLES["SUPPORT"], 14]:
        rules.manual_eliminate(session, run, f"Champ{i:03d}")
    session.commit()
    item, _ = shop.purchase(session, run, 1, "role")
    with pytest.raises(RuleError, match="No Support champions are alive"):
        shop.use_item(session, item, {"role": "UTILITY"})
    # Champ014 (mains bot, also plays support) back alone makes a support pool of one: allowed.
    rules.manual_revive(session, run, "Champ014")
    shop.use_item(session, item, {"role": "UTILITY"})
    game = rules.create_spin(session, run, [1, 2])
    assert rules.assignments_for(session, game.id)[0].options == ["Champ014"]  # one option: all there is


def test_reroll_stays_in_the_role(session, run):
    lock(session, run, 1, "JUNGLE")
    reroll, _ = shop.purchase(session, run, 1, "reroll")
    game = rules.create_spin(session, run, [1, 2], random.Random(5))
    before = list(rules.assignments_for(session, game.id)[0].options)
    shop.use_item(session, reroll, {"game_id": game.id}, random.Random(6))
    after = rules.assignments_for(session, game.id)[0].options
    assert set(after) <= champs(4, 5, 6, 7) and not set(after) & set(before)


def test_over_the_api(client, session, run):
    pid = 1
    res = client.post(f"/api/runs/{run.id}/players/{pid}/purchase", json={"type": "role"})
    assert res.status_code == 200 and res.json()["item"]["type"] == "role"
    item_id = res.json()["item"]["id"]
    assert client.post(f"/api/items/{item_id}/use", json={"role": "MIDDLE"}).json()["status"] == "armed"
    econ = {e["player_id"]: e for e in client.get(f"/api/runs/{run.id}/economy").json()}
    assert econ[pid]["armed_role"] == "MIDDLE"
    assert client.get(f"/api/runs/{run.id}/shop").json()["locked_roles"] == {"MIDDLE": pid}


def test_role_select_in_discord(session, world):  # noqa: F811
    run = session.get(type(world.run), world.run.id)
    for pos, ids in ROLES.items():
        for i in ids:
            c = session.get(Champion, f"Champ{i:03d}")
            c.positions = [pos]
            session.add(c)
    economy.record(session, run.id, 1, 1000, "manual_adjust")
    economy.record(session, run.id, 2, 100, "manual_adjust")
    session.commit()
    a = discord_bot.handle(session, cmd("roleselect", role="BOTTOM"))
    text = a.response["data"]["content"]
    assert "**Alex** locked **Bot**" in text and "bought for 400 gold" in text
    assert "flags" not in a.response["data"]  # everyone sees it
    # Bea can't take the same role, and can't afford one anyway.
    a = discord_bot.handle(session, cmd("roleselect", user="d-bea", role="BOTTOM"))
    assert a.response["data"]["flags"] == 64
    # The spin message says where the role came from.
    game = rules.create_spin(session, run, [1, 2])
    session.commit()
    from app.services import discord_render

    msg = discord_render.spin_message(session, game)
    assert any("Role: **Bot** (Role Select)" in e.get("description", "") for e in msg["embeds"])
    assert "roleselect" in {c["name"] for c in discord_bot.COMMANDS}
    assert session.exec(select(InventoryItem).where(InventoryItem.type == "role")).one().status == "used"
