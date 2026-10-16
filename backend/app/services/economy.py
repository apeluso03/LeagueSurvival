"""Gold (SPEC 7.7): earned per player per challenge game from Riot stats, kept as a ledger.

A balance is always the sum of the player's non-undone ledger rows for the run.
"""

from sqlmodel import Session, col, func, select

from app.models import ChallengeGame, GoldLedger, PlayerMatchStats, Run
from app.services import shop_config


def multikill_counts(pms: PlayerMatchStats, mode: str) -> dict[str, int]:
    d, t, q, p = pms.double_kills, pms.triple_kills, pms.quadra_kills, pms.penta_kills
    if mode == "highest":
        # Riot counts the double/triple/quadra inside a penta too; keep only the biggest one.
        d, t, q = max(d - t, 0), max(t - q, 0), max(q - p, 0)
    return {"double": d, "triple": t, "quadra": q, "penta": p}


def compute_gold(pms: PlayerMatchStats, cfg: dict) -> dict:
    """The gold one player earned in one game, with the per-source breakdown shown in the Shop."""
    g = cfg["gold"]
    support = pms.team_position == "UTILITY"
    damage_total = pms.damage_to_champs + ((pms.heals_on_teammates + pms.shields_on_teammates) if support else 0)
    multis = multikill_counts(pms, g["multikill_mode"])
    parts = {
        "kills": g["kill"] * pms.kills,
        "assists": g["assist"] * pms.assists,
        "damage": g["damage_gold"] * (damage_total // g["damage_step"]),
        "vision": g["vision_gold"] * (pms.vision_score // g["vision_step"]),
        "multikills": sum(g[k] * n for k, n in multis.items()),
    }
    return {
        **parts,
        "total": sum(parts.values()),
        "support_bonus": support,
        "damage_counted": damage_total,
        "multikill_counts": multis,
        "stats": {"kills": pms.kills, "deaths": pms.deaths, "assists": pms.assists, "vision": pms.vision_score},
        "grade": pms.rating_grade,
    }


def balance(session: Session, run_id: int, player_id: int) -> int:
    total = session.exec(
        select(func.coalesce(func.sum(GoldLedger.amount), 0)).where(
            GoldLedger.run_id == run_id, GoldLedger.player_id == player_id, col(GoldLedger.undone).is_(False)
        )
    ).one()
    return int(total)


def totals(session: Session, run_id: int, player_id: int) -> dict:
    rows = session.exec(
        select(GoldLedger).where(
            GoldLedger.run_id == run_id, GoldLedger.player_id == player_id, col(GoldLedger.undone).is_(False)
        )
    ).all()
    earned = sum(r.amount for r in rows if r.amount > 0)
    spent = -sum(r.amount for r in rows if r.amount < 0 and r.reason == "purchase")
    return {"balance": sum(r.amount for r in rows), "earned": earned, "spent": spent}


def ledger(session: Session, run_id: int, player_id: int) -> list[GoldLedger]:
    return list(
        session.exec(
            select(GoldLedger)
            .where(GoldLedger.run_id == run_id, GoldLedger.player_id == player_id)
            .order_by(col(GoldLedger.id).desc())
        ).all()
    )


def record(session: Session, run_id: int, player_id: int, amount: int, reason: str, **fields) -> GoldLedger:
    row = GoldLedger(run_id=run_id, player_id=player_id, amount=amount, reason=reason, **fields)
    session.add(row)
    session.flush()
    return row


def award_game(session: Session, game: ChallengeGame) -> list[GoldLedger]:
    """Pay out gold for a resolved challenge game that is linked to a Riot match, then settle
    contracts. Safe to call more than once: players already paid for this game are skipped."""
    from app.services import contracts, rules  # local: rules imports this module

    if game.status not in ("won", "lost") or not game.riot_match_id:
        return []
    run = session.get(Run, game.run_id)
    cfg = shop_config.effective(run.shop_config)
    paid = set(
        session.exec(
            select(GoldLedger.player_id).where(
                GoldLedger.game_id == game.id, GoldLedger.reason == "game", col(GoldLedger.undone).is_(False)
            )
        ).all()
    )
    rows = []
    for a in rules.assignments_for(session, game.id):
        if a.player_id in paid:
            continue
        pms = session.get(PlayerMatchStats, (game.riot_match_id, a.player_id))
        if pms is None:
            continue
        breakdown = compute_gold(pms, cfg)
        rows.append(record(session, run.id, a.player_id, breakdown["total"], "game", game_id=game.id, breakdown=breakdown))
        contracts.resolve_for_player(session, game, a.player_id, pms, cfg)
    return rows


def reverse_game(session: Session, game: ChallengeGame) -> None:
    """Undo every gold change a game's result caused (game gold and contract payouts)."""
    from app.services import contracts

    for row in session.exec(
        select(GoldLedger).where(GoldLedger.game_id == game.id, col(GoldLedger.undone).is_(False))
    ).all():
        if row.reason in ("game", "contract_payout"):
            row.undone = True
            session.add(row)
    contracts.reopen_for_game(session, game)
    session.flush()


def game_gold(session: Session, game_id: int) -> dict[int, int]:
    """Gold each player earned from a game (game gold plus contract payouts)."""
    out: dict[int, int] = {}
    for row in session.exec(
        select(GoldLedger).where(
            GoldLedger.game_id == game_id,
            col(GoldLedger.reason).in_(["game", "contract_payout"]),
            col(GoldLedger.undone).is_(False),
        )
    ).all():
        out[row.player_id] = out.get(row.player_id, 0) + row.amount
    return out
