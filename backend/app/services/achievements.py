"""Achievements and titles (Trophies tab).

Worked out from history every time (nothing extra is stored), so they cover past games too and
undoing a game takes its achievements back. Each unlock remembers the game (when there is one), so
the app can announce the ones a game just earned.
"""

from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime

from sqlmodel import Session, col, select

from app.models import (
    ChallengeGame,
    Contract,
    GoldLedger,
    InventoryItem,
    Player,
    PlayerMatchStats,
    PoolEvent,
    ReviveToken,
    SpinAssignment,
)


@dataclass(frozen=True)
class Achievement:
    id: str
    name: str
    description: str
    title: str  # what a player can show under their name
    icon: str
    tier: str  # "bronze" | "silver" | "gold" | "prismatic"


CATALOG = [
    Achievement("first_win", "First Blood", "Win your first challenge game", "the Initiated", "🩸", "bronze"),
    Achievement("streak3", "Heating Up", "Win 3 of your games in a row", "the Warm", "🔥", "bronze"),
    Achievement("streak5", "On Fire", "Win 5 of your games in a row", "the Blazing", "☄️", "silver"),
    Achievement("streak10", "Unstoppable", "Win 10 of your games in a row", "the Unstoppable", "⚡", "prismatic"),
    Achievement("veteran", "Veteran", "Play 50 challenge games", "the Veteran", "🎖️", "silver"),
    Achievement("fate", "Fate's Chosen", "Win 10 games on your #1 option", "Fate's Favourite", "🎯", "silver"),
    Achievement("off_script", "Off Script", "Win on a champion that wasn't one of your options", "the Rebel", "🃏", "silver"),
    Achievement("called_it", "Called It", "Win with a champion you picked with Choose a Champ", "the Oracle", "🔮", "silver"),
    Achievement("penta", "Pentakill", "Get a pentakill in a challenge game", "the Pentakiller", "🖐️", "prismatic"),
    Achievement("quadra", "So Close", "Get a quadra kill in a challenge game", "the Almost", "✋", "gold"),
    Achievement("deathless", "Untouchable", "Win a challenge game without dying", "the Untouchable", "🛡️", "gold"),
    Achievement("carry", "One-Person Army", "Win with 15 or more kills", "the Carry", "💪", "gold"),
    Achievement("s_tier", "S-Tier", "Earn an S grade or better", "the Exceptional", "🏅", "silver"),
    Achievement("flawless", "Flawless", "Earn an S+ grade", "the Flawless", "💎", "prismatic"),
    Achievement("gray_screen", "Gray Screen Enthusiast", "Die 12 or more times in one game", "the Feeder", "🪦", "bronze"),
    Achievement("patient_zero", "Patient Zero", "Lose the first champion of a run", "Patient Zero", "🦠", "bronze"),
    Achievement("reaper", "The Reaper", "Lose 10 champions", "the Reaper", "💀", "gold"),
    Achievement("necromancer", "Necromancer", "Use 3 revive tokens", "the Necromancer", "🧟", "silver"),
    Achievement("bodyguard", "Bodyguard", "Have a shield you placed save a champion", "the Bodyguard", "🦺", "silver"),
    Achievement("contractor", "Contractor", "Complete 3 contracts", "the Contractor", "📜", "gold"),
    Achievement("whale", "Whale", "Spend 5,000 gold in the shop", "the Whale", "🐋", "gold"),
    Achievement("marathon", "Marathon", "Play in a run's 20th win", "the Marathoner", "🏃", "gold"),
]
BY_ID = {a.id: a for a in CATALOG}
GRADES_S = {"S+", "S", "S-"}


@dataclass
class Unlock:
    id: str
    game_id: int | None
    at: datetime


def evaluate(session: Session) -> dict[int, dict[str, Unlock]]:
    """Every player's unlocked achievements (first time each was earned)."""
    out: dict[int, dict[str, Unlock]] = defaultdict(dict)

    def unlock(pid: int | None, aid: str, game_id: int | None, at: datetime) -> None:
        if pid is not None and aid not in out[pid]:
            out[pid][aid] = Unlock(aid, game_id, at)

    rows = session.exec(
        select(SpinAssignment, ChallengeGame)
        .join(ChallengeGame, col(ChallengeGame.id) == col(SpinAssignment.game_id))
        .where(col(ChallengeGame.status).in_(["won", "lost"]))
        .order_by(col(ChallengeGame.id))
    ).all()
    chosen = {
        (i.player_id, i.used_in_game_id): i.target.get("champion_id")
        for i in session.exec(select(InventoryItem).where(InventoryItem.type == "choose", InventoryItem.status == "used")).all()
    }

    per_player: dict[int, list] = defaultdict(list)
    run_wins: dict[int, int] = defaultdict(int)
    for a, g in rows:
        per_player[a.player_id].append((a, g))
    # The game that was each run's 20th win.
    twentieth: set[int] = set()
    seen_games: set[int] = set()
    for _, g in rows:
        if g.id in seen_games:
            continue
        seen_games.add(g.id)
        if g.status == "won":
            run_wins[g.run_id] += 1
            if run_wins[g.run_id] == 20:
                twentieth.add(g.id)

    for pid, games in per_player.items():
        streak = fate = 0
        for n, (a, g) in enumerate(games, start=1):
            won = g.status == "won"
            at = g.resolved_at or g.created_at
            streak = streak + 1 if won else 0
            if won:
                unlock(pid, "first_win", g.id, at)
            for need, aid in ((3, "streak3"), (5, "streak5"), (10, "streak10")):
                if streak >= need:
                    unlock(pid, aid, g.id, at)
            if n >= 50:
                unlock(pid, "veteran", g.id, at)
            if won and a.played_option_index == 0:
                fate += 1
                if fate >= 10:
                    unlock(pid, "fate", g.id, at)
            if won and a.played_champion_id and a.played_option_index is None:
                unlock(pid, "off_script", g.id, at)
            if won and a.played_champion_id and chosen.get((pid, g.id)) == a.played_champion_id:
                unlock(pid, "called_it", g.id, at)
            if g.id in twentieth:
                unlock(pid, "marathon", g.id, at)
            pms = session.get(PlayerMatchStats, (g.riot_match_id, pid)) if g.riot_match_id else None
            if pms is None:
                continue
            if pms.penta_kills:
                unlock(pid, "penta", g.id, at)
            if pms.quadra_kills or pms.penta_kills:
                unlock(pid, "quadra", g.id, at)
            if won and pms.deaths == 0:
                unlock(pid, "deathless", g.id, at)
            if won and pms.kills >= 15:
                unlock(pid, "carry", g.id, at)
            if pms.rating_grade in GRADES_S:
                unlock(pid, "s_tier", g.id, at)
            if pms.rating_grade == "S+":
                unlock(pid, "flawless", g.id, at)
            if pms.deaths >= 12:
                unlock(pid, "gray_screen", g.id, at)

    # Eliminations: Patient Zero (a run's first) and The Reaper (10 total).
    elims = session.exec(
        select(PoolEvent).where(PoolEvent.type == "eliminate", col(PoolEvent.undone).is_(False)).order_by(col(PoolEvent.id))
    ).all()
    first_in_run: set[int] = set()
    lost: dict[int, int] = defaultdict(int)
    for e in elims:
        if e.player_id is None:
            continue
        if e.run_id not in first_in_run:
            first_in_run.add(e.run_id)
            unlock(e.player_id, "patient_zero", e.game_id, e.created_at)
        lost[e.player_id] += 1
        if lost[e.player_id] == 10:
            unlock(e.player_id, "reaper", e.game_id, e.created_at)

    used: dict[int, int] = defaultdict(int)
    for t in session.exec(select(ReviveToken).where(col(ReviveToken.used_at).is_not(None)).order_by(col(ReviveToken.used_at))).all():
        used[t.player_id] += 1
        if used[t.player_id] == 3:
            unlock(t.player_id, "necromancer", None, t.used_at)

    owners = {i.id: i.player_id for i in session.exec(select(InventoryItem).where(InventoryItem.type == "shield")).all()}
    for e in session.exec(
        select(PoolEvent).where(PoolEvent.type == "shield_consumed", col(PoolEvent.undone).is_(False)).order_by(col(PoolEvent.id))
    ).all():
        unlock(owners.get(e.item_id), "bodyguard", e.game_id, e.created_at)

    won_contracts: dict[int, int] = defaultdict(int)
    for c, item in session.exec(
        select(Contract, InventoryItem)
        .join(InventoryItem, col(InventoryItem.id) == col(Contract.item_id))
        .where(Contract.status == "won")
        .order_by(col(Contract.item_id))
    ).all():
        won_contracts[item.player_id] += 1
        if won_contracts[item.player_id] == 3:
            unlock(item.player_id, "contractor", c.game_id, item.used_at or item.purchased_at)

    spent: dict[int, int] = defaultdict(int)
    for row in session.exec(
        select(GoldLedger).where(GoldLedger.reason == "purchase", col(GoldLedger.undone).is_(False)).order_by(col(GoldLedger.id))
    ).all():
        spent[row.player_id] -= row.amount
        if spent[row.player_id] >= 5000:
            unlock(row.player_id, "whale", None, row.created_at)

    return out


def report(session: Session) -> dict:
    unlocked = evaluate(session)
    players = session.exec(select(Player)).all()
    active = [p.id for p in players if p.id in unlocked or session.exec(
        select(SpinAssignment.id).where(SpinAssignment.player_id == p.id).limit(1)
    ).first()]
    rarity = {
        a.id: (sum(a.id in unlocked.get(pid, {}) for pid in active) / len(active)) if active else 0.0 for a in CATALOG
    }
    return {
        "catalog": [asdict(a) for a in CATALOG],
        "rarity": rarity,
        "players": {
            pid: sorted((asdict(u) for u in found.values()), key=lambda u: u["at"]) for pid, found in unlocked.items()
        },
    }
