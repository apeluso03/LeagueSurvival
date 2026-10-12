"""Contracts (SPEC 7.9): buy for 100, get a random goal, complete it in your next challenge game
with Riot data to earn a flat payout.

A contract is settled by the first game that (a) was spun after the contract was bought, (b) the
player played in, and (c) has Riot stats. Oldest contract first, one per game. Void games and games
the player sat out never touch it, so it simply waits (the spec's "refund on void").
"""

import random

from sqlmodel import Session, col, select

from app.models import ChallengeGame, Contract, InventoryItem, PlayerMatchStats, utcnow
from app.services import rating

GOALS = ("kills", "assists", "win", "rating")


def create(session: Session, item: InventoryItem, cfg: dict, rng: random.Random | None = None) -> Contract:
    goal = (rng or random.SystemRandom()).choice(GOALS)
    c = cfg["contract"]
    target = {"kills": str(c["kills"]), "assists": str(c["assists"]), "win": "win", "rating": c["rating"]}[goal]
    contract = Contract(item_id=item.id, goal_type=goal, target=target, payout=c["payout"])
    session.add(contract)
    session.flush()
    return contract


def describe(contract: Contract) -> str:
    return {
        "kills": f"Get {contract.target}+ kills",
        "assists": f"Get {contract.target}+ assists",
        "win": "Win the game",
        "rating": f"Get an {contract.target} rating or better",
    }[contract.goal_type]


def met(contract: Contract, game: ChallengeGame, pms: PlayerMatchStats) -> bool:
    if contract.goal_type == "kills":
        return pms.kills >= int(contract.target)
    if contract.goal_type == "assists":
        return pms.assists >= int(contract.target)
    if contract.goal_type == "win":
        return game.status == "won"
    return rating.at_least(pms.rating_grade, contract.target)


def pending_for(session: Session, run_id: int, player_id: int) -> list[tuple[Contract, InventoryItem]]:
    return list(
        session.exec(
            select(Contract, InventoryItem)
            .join(InventoryItem, col(InventoryItem.id) == col(Contract.item_id))
            .where(
                InventoryItem.run_id == run_id,
                InventoryItem.player_id == player_id,
                Contract.status == "pending",
            )
            .order_by(col(InventoryItem.purchased_at), col(InventoryItem.id))
        ).all()
    )


def resolve_for_player(session: Session, game: ChallengeGame, player_id: int, pms: PlayerMatchStats, cfg: dict):
    from app.services import economy

    for contract, item in pending_for(session, game.run_id, player_id):
        if item.purchased_at >= game.created_at:
            return None  # bought after this spin: it waits for the next game
        won = met(contract, game, pms)
        contract.status = "won" if won else "lost"
        contract.game_id = game.id
        item.status = "used"
        item.used_at = utcnow()
        item.used_in_game_id = game.id
        session.add_all([contract, item])
        if won:
            economy.record(
                session, game.run_id, player_id, contract.payout, "contract_payout", game_id=game.id, item_id=item.id,
                breakdown={"goal": describe(contract)},
            )
        session.flush()
        return contract  # one contract per game
    return None


def reopen_for_game(session: Session, game: ChallengeGame) -> None:
    """Undo: contracts settled by this game go back to waiting."""
    for contract in session.exec(select(Contract).where(Contract.game_id == game.id)).all():
        item = session.get(InventoryItem, contract.item_id)
        contract.status = "pending"
        contract.game_id = None
        item.status = "active"
        item.used_at = None
        item.used_in_game_id = None
        session.add_all([contract, item])
    session.flush()
