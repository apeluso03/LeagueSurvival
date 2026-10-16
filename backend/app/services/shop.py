"""Shop and items (SPEC 7.8): catalog, purchases and item effects.

Items belong to one player in one run and can only act on that player's own spin. In the MVP the
run owner buys and uses items for everyone; the data already records whose item it is.
"""

import math
import random

from sqlmodel import Session, col, select

from app.models import ChallengeGame, Contract, InventoryItem, Player, PoolEntry, PoolEvent, Run, utcnow
from app.services import contracts, economy, rules, shop_config
from app.services import spin as spin_logic
from app.services.rules import RuleError

ITEMS = {
    "reroll": ("Reroll", "After a spin, before lock-in", "Swap your whole list for a fresh roll."),
    "blacklist": ("Blacklist", "Before a spin", "Ban a few champions from your next roll."),
    "swap": ("Swap", "After a spin, before lock-in", "Trade your list with another player in the same spin."),
    "shield": ("Shield", "Anytime", "Protect an alive champion. The next loss that would eliminate it uses the shield instead."),
    "choose": ("Choose a Champ", "After a spin, before lock-in", "Replace your list with any alive champion you pick."),
    "contract": ("Contract", "Before a spin", "Get a random goal for your next game. Hit it for bonus gold."),
}


def blacklist_cap(alive_count: int, pct: float) -> int:
    """ceil(pct x alive), e.g. 87 alive at 5% allows 5, 20 alive allows 1."""
    return math.ceil(round(pct * alive_count, 9)) if alive_count > 0 else 0


def catalog(session: Session, run: Run) -> dict:
    cfg = shop_config.effective(run.shop_config)
    alive = len(rules.alive_champion_ids(session, run.id))
    return {
        "items": [
            {"type": t, "name": n, "price": cfg["prices"][t], "when": w, "description": d}
            for t, (n, w, d) in ITEMS.items()
        ],
        "blacklist_cap": blacklist_cap(alive, cfg["blacklist_pct"]),
        "contract_payout": cfg["contract"]["payout"],
        "config": cfg,
    }


def armed_blacklists(session: Session, run_id: int, player_ids: list[int]) -> dict[int, tuple[InventoryItem, set[str]]]:
    rows = session.exec(
        select(InventoryItem).where(
            InventoryItem.run_id == run_id,
            InventoryItem.type == "blacklist",
            InventoryItem.status == "armed",
            col(InventoryItem.player_id).in_(player_ids),
        )
    ).all()
    return {i.player_id: (i, set(i.target.get("champion_ids", []))) for i in rows}


def inventory(session: Session, run_id: int, player_id: int) -> list[tuple[InventoryItem, Contract | None]]:
    items = session.exec(
        select(InventoryItem)
        .where(InventoryItem.run_id == run_id, InventoryItem.player_id == player_id)
        .order_by(col(InventoryItem.id).desc())
    ).all()
    return [(i, session.get(Contract, i.id) if i.type == "contract" else None) for i in items]


def purchase(
    session: Session, run: Run, player_id: int, item_type: str, rng: random.Random | None = None
) -> tuple[InventoryItem, Contract | None]:
    if run.status != "active":
        raise RuleError("This run has ended", 409)
    if item_type not in ITEMS:
        raise RuleError(f"Unknown item: {item_type}")
    player = session.get(Player, player_id)
    if player is None:
        raise RuleError(f"Unknown player {player_id}", 404)
    cfg = shop_config.effective(run.shop_config)
    price = cfg["prices"][item_type]
    gold = economy.balance(session, run.id, player_id)
    if gold < price:
        raise RuleError(f"{player.display_name} has {gold} gold and {ITEMS[item_type][0]} costs {price}.", 409)

    item = InventoryItem(run_id=run.id, player_id=player_id, type=item_type, price_paid=price)
    session.add(item)
    session.flush()
    economy.record(session, run.id, player_id, -price, "purchase", item_id=item.id, breakdown={"item": item_type})
    contract = None
    if item_type == "contract":
        item.status = "active"  # a contract is live as soon as it's bought
        session.add(item)
        contract = contracts.create(session, item, cfg, rng)
    session.flush()
    return item, contract


# --- using items ----------------------------------------------------------------------


def _spin_slot(session: Session, item: InventoryItem, game_id: int | None):
    """Checks shared by Reroll / Swap / Choose: a pending challenge game the owner is in, before lock-in."""
    if game_id is None:
        raise RuleError("Pick the game to use this on")
    game = session.get(ChallengeGame, game_id)
    if game is None or game.run_id != item.run_id:
        raise RuleError("That game isn't in this run", 404)
    if game.status != "pending":
        raise RuleError("This only works on a game that hasn't been played yet", 409)
    mine = next((a for a in rules.assignments_for(session, game.id) if a.player_id == item.player_id), None)
    if mine is None:
        raise RuleError("You can only use this on your own spin", 409)
    if mine.played_champion_id:
        raise RuleError("Too late: the champion played is already recorded", 409)
    return game, mine


def _spend(session: Session, item: InventoryItem, game_id: int | None, target: dict) -> None:
    item.status = "used"
    item.used_at = utcnow()
    item.used_in_game_id = game_id
    item.target = target
    session.add(item)


def use_item(session: Session, item: InventoryItem, payload: dict, rng: random.Random | None = None) -> InventoryItem:
    run = session.get(Run, item.run_id)
    if run.status != "active":
        raise RuleError("This run has ended", 409)
    if item.status != "unused":
        raise RuleError("This item has already been used", 409)
    cfg = shop_config.effective(run.shop_config)
    alive = rules.alive_champion_ids(session, run.id)

    if item.type == "shield":
        cid = payload.get("champion_id")
        entry = session.get(PoolEntry, (run.id, cid)) if cid else None
        if entry is None:
            raise RuleError("Pick a champion in this run's pool", 404)
        if entry.status != "alive":
            raise RuleError("Shields only go on alive champions", 409)
        if entry.shield_item_id:
            raise RuleError("That champion already has a shield", 409)
        entry.shield_item_id = item.id
        item.status = "active"
        item.used_at = utcnow()
        item.target = {"champion_id": cid}
        session.add_all([entry, item])
        session.add(PoolEvent(run_id=run.id, type="shield_placed", champion_id=cid, player_id=item.player_id, item_id=item.id))

    elif item.type == "blacklist":
        ids = list(dict.fromkeys(payload.get("champion_ids") or []))
        cap = blacklist_cap(len(alive), cfg["blacklist_pct"])
        if not 1 <= len(ids) <= cap:
            raise RuleError(f"Pick between 1 and {cap} champions")
        if any(c not in alive for c in ids):
            raise RuleError("You can only blacklist alive champions")
        if armed_blacklists(session, run.id, [item.player_id]):
            raise RuleError("This player already has a blacklist ready for their next spin", 409)
        item.status = "armed"
        item.target = {"champion_ids": ids, "cap": cap}
        session.add(item)

    elif item.type == "reroll":
        game, mine = _spin_slot(session, item, payload.get("game_id"))
        others = {c for a in rules.assignments_for(session, game.id) if a.player_id != item.player_id for c in a.options}
        bl = session.exec(
            select(InventoryItem).where(
                InventoryItem.type == "blacklist",
                InventoryItem.player_id == item.player_id,
                InventoryItem.used_in_game_id == game.id,
            )
        ).first()
        banned = set(bl.target.get("champion_ids", [])) if bl else set()
        count = max(len(mine.options), 1)
        try:
            new = spin_logic.redraw(alive, count, set(mine.options) | others | banned, rng)
        except spin_logic.SpinBlocked as e:
            raise RuleError(str(e), 409) from e
        old = list(mine.options)
        mine.options = new
        session.add(mine)
        _spend(session, item, game.id, {"old": old, "new": new})

    elif item.type == "swap":
        game, mine = _spin_slot(session, item, payload.get("game_id"))
        other_id = payload.get("other_player_id")
        other = next((a for a in rules.assignments_for(session, game.id) if a.player_id == other_id), None)
        if other is None or other_id == item.player_id:
            raise RuleError("Pick another player in this spin", 409)
        if other.played_champion_id:
            raise RuleError("Too late: that player's champion is already recorded", 409)
        mine.options, other.options = list(other.options), list(mine.options)
        session.add_all([mine, other])
        _spend(session, item, game.id, {"player_id": other_id})

    elif item.type == "choose":
        game, mine = _spin_slot(session, item, payload.get("game_id"))
        cid = payload.get("champion_id")
        if cid not in alive:
            raise RuleError("Pick an alive champion", 409)
        taken = {c for a in rules.assignments_for(session, game.id) if a.player_id != item.player_id for c in a.options}
        if cid in taken:
            raise RuleError("That champion is on another player's list in this spin", 409)
        mine.options = [cid]
        session.add(mine)
        _spend(session, item, game.id, {"champion_id": cid})

    else:  # contract
        raise RuleError("A contract starts as soon as it's bought; there's nothing to use", 409)

    session.flush()
    return item


def adjust_gold(session: Session, run: Run, player_id: int, amount: int, note: str | None):
    if amount == 0:
        raise RuleError("Enter an amount other than 0")
    if session.get(Player, player_id) is None:
        raise RuleError(f"Unknown player {player_id}", 404)
    return economy.record(session, run.id, player_id, amount, "manual_adjust", breakdown={"note": note or ""})


def items_used_in_game(session: Session, game_id: int) -> list[InventoryItem]:
    """Reroll / Swap / Choose / Blacklist items spent on a game's spin (History tab)."""
    return list(
        session.exec(
            select(InventoryItem).where(
                InventoryItem.used_in_game_id == game_id, col(InventoryItem.type).in_(["reroll", "swap", "choose", "blacklist"])
            )
        ).all()
    )
