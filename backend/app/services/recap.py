"""Run recap and player profile pages: read-only summaries built from the existing tables."""

from collections import Counter, defaultdict
from dataclasses import asdict

from sqlmodel import Session, col, select

from app.models import (
    ChallengeGame,
    GoldLedger,
    InventoryItem,
    Player,
    PlayerMatchStats,
    PoolEntry,
    PoolEvent,
    ReviveToken,
    Run,
    SpinAssignment,
)
from app.services import economy, rating, stats

MULTIKILLS = ("penta_kills", "quadra_kills", "triple_kills", "double_kills")


def _resolved_games(session: Session, run_id: int | None = None) -> list[ChallengeGame]:
    q = select(ChallengeGame).where(col(ChallengeGame.status).in_(["won", "lost"]))
    if run_id is not None:
        q = q.where(ChallengeGame.run_id == run_id)
    return list(session.exec(q.order_by(col(ChallengeGame.id))).all())


def _eliminations(session: Session, run_id: int | None = None) -> list[PoolEvent]:
    q = select(PoolEvent).where(PoolEvent.type == "eliminate", col(PoolEvent.undone).is_(False))
    if run_id is not None:
        q = q.where(PoolEvent.run_id == run_id)
    return list(session.exec(q.order_by(col(PoolEvent.id))).all())


def _record(wins: int, games: int) -> str:
    return f"{wins}–{games - wins}"


# --- run recap ------------------------------------------------------------------------------


def run_recap(session: Session, run: Run) -> dict:
    games = _resolved_games(session, run.id)
    game_ids = [g.id for g in games]
    won = {g.id for g in games if g.status == "won"}
    assignments = (
        session.exec(select(SpinAssignment).where(col(SpinAssignment.game_id).in_(game_ids))).all() if game_ids else []
    )
    pids = sorted({a.player_id for a in assignments})
    per_player = {s.player_id: s for s in stats.player_stats(session, pids, run.id)}
    elims = _eliminations(session, run.id)
    tokens = session.exec(select(ReviveToken).where(ReviveToken.run_id == run.id)).all()
    items = session.exec(
        select(InventoryItem).where(InventoryItem.run_id == run.id, InventoryItem.status != "refunded")
    ).all()
    shields_saved = session.exec(
        select(PoolEvent).where(
            PoolEvent.run_id == run.id, PoolEvent.type == "shield_consumed", col(PoolEvent.undone).is_(False)
        )
    ).all()
    pool = session.exec(select(PoolEntry).where(PoolEntry.run_id == run.id)).all()
    lines = stats.run_champion_lines(session, run.id)

    multikills: dict[int, Counter] = defaultdict(Counter)
    for g in games:
        if not g.riot_match_id:
            continue
        for pms in session.exec(select(PlayerMatchStats).where(PlayerMatchStats.match_id == g.riot_match_id)).all():
            if pms.player_id in per_player:
                for k in MULTIKILLS:
                    multikills[pms.player_id][k] += getattr(pms, k)

    played_by: dict[int, Counter] = defaultdict(Counter)
    for a in assignments:
        if a.played_champion_id and a.game_id in game_ids:
            played_by[a.player_id][a.played_champion_id] += 1
    elims_by = Counter(e.player_id for e in elims if e.player_id is not None)
    tokens_by = Counter(t.player_id for t in tokens)
    players = []
    for pid in pids:
        s = per_player[pid]
        best = s.best_champions[0] if s.best_champions else None
        players.append(
            {
                **{k: v for k, v in asdict(s).items() if k not in ("best_champions", "eliminated_champions")},
                "eliminations": elims_by[pid],
                "tokens_earned": tokens_by[pid],
                "multikills": {k.removesuffix("_kills"): multikills[pid][k] for k in MULTIKILLS},
                "best_champion": asdict(best) if best else None,
                "top_champion": played_by[pid].most_common(1)[0][0] if played_by[pid] else None,
            }
        )

    return {
        "run": {
            "id": run.id,
            "name": run.name,
            "status": run.status,
            "started_at": run.started_at,
            "ended_at": run.ended_at,
        },
        "totals": {
            "games": len(games),
            "wins": len(won),
            "losses": len(games) - len(won),
            "best_streak": run.best_streak,
            "alive": sum(e.status == "alive" for e in pool),
            "total": len(pool),
            "tokens_earned": len(tokens),
            "tokens_used": sum(t.used_at is not None for t in tokens),
            "shields_saved": len(shields_saved),
            "items_bought": len(items),
            "gold_earned": sum(p["gold_earned"] or 0 for p in players),
            "gold_spent": sum(p["gold_spent"] or 0 for p in players),
        },
        "timeline": [{"game_id": g.id, "status": g.status, "created_at": g.created_at} for g in games],
        "players": players,
        "awards": _awards(players, elims, pool, lines),
    }


def _top(items: list, key):
    """The single best item by `key`, or None when it's tied for first (no award beats a coin flip)."""
    if not items:
        return None
    ranked = sorted(items, key=key, reverse=True)
    if len(ranked) > 1 and key(ranked[0]) == key(ranked[1]):
        return None
    return ranked[0]


def _awards(players: list[dict], elims: list[PoolEvent], pool: list[PoolEntry], lines: dict) -> list[dict]:
    out: list[dict] = []

    def add(id_: str, title: str, text: str, player_id: int | None = None, champion_id: str | None = None):
        out.append({"id": id_, "title": title, "text": text, "player_id": player_id, "champion_id": champion_id})

    played = [p for p in players if p["games"]]
    if played:
        # MVP: best win rate among players with at least half as many games as the busiest one.
        floor = max(p["games"] for p in played) / 2
        mvp = _top(
            [p for p in played if p["games"] >= floor],
            key=lambda p: (p["win_rate"] or 0, p["games"], p["kda"] or 0),
        )
        if mvp:
            add("mvp", "MVP", f"Best record: {_record(mvp['wins'], mvp['games'])}", mvp["player_id"])

    p = _top([p for p in players if p["kda"] is not None], key=lambda p: p["kda"])
    if p:
        add("kda", "Cleanest hands", f"Best KDA: {p['kda']:.1f}", p["player_id"])

    p = _top([p for p in players if p["avg_grade"]], key=lambda p: -rating.GRADES.index(p["avg_grade"]))
    if p:
        add("grade", "Top marks", f"Average grade {p['avg_grade']}", p["player_id"])

    order = ("penta", "quadra", "triple", "double")
    p = _top([p for p in players if any(p["multikills"].values())], key=lambda p: tuple(p["multikills"][k] for k in order))
    if p:
        kind = next(k for k in order if p["multikills"][k])
        n = p["multikills"][kind]
        add("multikill", "Multikill king", f"{n} {kind}kill{'s' if n > 1 else ''}", p["player_id"])

    reaper = _top([p for p in players if p["eliminations"]], key=lambda p: p["eliminations"])
    if reaper:
        n = reaper["eliminations"]
        add("reaper", "Grim reaper", f"Lost the most champs: {n}", reaper["player_id"])

    spender = _top([p for p in players if p["gold_spent"]], key=lambda p: p["gold_spent"])
    if spender:
        add("spender", "Big spender", f"Spent {spender['gold_spent']:,} gold in the shop", spender["player_id"])

    if elims:
        first = elims[0]
        add("first", "First to fall", "The first champ eliminated", first.player_id, first.champion_id)

    alive = {e.champion_id for e in pool if e.status == "alive"}
    survivors = [(cid, line) for cid, line in lines.items() if cid in alive and line.offered]
    if survivors:
        cid, line = max(survivors, key=lambda x: (x[1].offered, x[1].wins))
        add("survivor", "Survivor", f"Rolled {line.offered} times and still standing", champion_id=cid)

    workhorses = [(cid, line) for cid, line in lines.items() if line.played > 1]
    if workhorses:
        cid, line = max(workhorses, key=lambda x: (x[1].played, x[1].wins))
        add("workhorse", "Workhorse", f"Played {line.played} times ({_record(line.wins, line.played)})", champion_id=cid)
    return out


# --- player profile ---------------------------------------------------------------------------


def player_profile(session: Session, player: Player, run_id: int | None) -> dict:
    pid = player.id
    s = stats.player_stats(session, [pid], run_id)[0]

    q = (
        select(SpinAssignment, ChallengeGame)
        .join(ChallengeGame, col(ChallengeGame.id) == col(SpinAssignment.game_id))
        .where(SpinAssignment.player_id == pid, col(ChallengeGame.status).in_(["won", "lost"]))
    )
    if run_id is not None:
        q = q.where(ChallengeGame.run_id == run_id)
    rows = session.exec(q.order_by(col(ChallengeGame.id).desc())).all()
    game_ids = [g.id for _, g in rows]

    def by_game(model, *where) -> set[int]:
        if not game_ids:
            return set()
        return set(session.exec(select(model).where(*where)).all())

    eliminated = by_game(
        PoolEvent.game_id,
        PoolEvent.type == "eliminate",
        col(PoolEvent.undone).is_(False),
        PoolEvent.player_id == pid,
        col(PoolEvent.game_id).in_(game_ids),
    )
    tokens = by_game(ReviveToken.earned_in_game_id, ReviveToken.player_id == pid, col(ReviveToken.earned_in_game_id).in_(game_ids))
    gold: dict[int, int] = defaultdict(int)
    if game_ids:
        for row in session.exec(
            select(GoldLedger).where(
                GoldLedger.player_id == pid,
                col(GoldLedger.game_id).in_(game_ids),
                col(GoldLedger.reason).in_(["game", "contract_payout"]),
                col(GoldLedger.undone).is_(False),
            )
        ).all():
            gold[row.game_id] += row.amount

    games = []
    champs: dict[str, list[bool]] = defaultdict(list)
    for a, g in rows:
        pms = session.get(PlayerMatchStats, (g.riot_match_id, pid)) if g.riot_match_id else None
        if a.played_champion_id:
            champs[a.played_champion_id].append(g.status == "won")
        games.append(
            {
                "game_id": g.id,
                "run_id": g.run_id,
                "created_at": g.created_at,
                "status": g.status,
                "champion_id": a.played_champion_id,
                "options": a.options,
                "grade": pms.rating_grade if pms else None,
                "kda": [pms.kills, pms.deaths, pms.assists] if pms else None,
                "gold": gold.get(g.id),
                "eliminated": g.id in eliminated,
                "token_earned": g.id in tokens,
            }
        )

    run_rows = session.exec(
        select(ChallengeGame.run_id, ChallengeGame.status)
        .join(SpinAssignment, col(SpinAssignment.game_id) == col(ChallengeGame.id))
        .where(SpinAssignment.player_id == pid, col(ChallengeGame.status).in_(["won", "lost"]))
    ).all()
    per_run: dict[int, list[bool]] = defaultdict(list)
    for rid, status in run_rows:
        per_run[rid].append(status == "won")
    runs = []
    for rid, results in sorted(per_run.items(), reverse=True):
        r = session.get(Run, rid)
        runs.append({"run_id": rid, "name": r.name, "status": r.status, "games": len(results), "wins": sum(results)})

    item_q = select(InventoryItem).where(InventoryItem.player_id == pid, InventoryItem.status != "refunded")
    if run_id is not None:
        item_q = item_q.where(InventoryItem.run_id == run_id)
    items: dict[str, dict[str, int]] = defaultdict(lambda: {"bought": 0, "used": 0})
    for i in session.exec(item_q).all():
        items[i.type]["bought"] += 1
        items[i.type]["used"] += i.status in ("used", "active", "armed")

    timeline = []
    if run_id is not None:
        bal = 0
        for row in reversed(economy.ledger(session, run_id, pid)):  # ledger is newest first
            if not row.undone:
                bal += row.amount
                timeline.append({"at": row.created_at, "balance": bal, "amount": row.amount, "reason": row.reason})

    return {
        "player": {
            "id": pid,
            "display_name": player.display_name,
            "riot_id": f"{player.riot_game_name}#{player.riot_tag_line}" if player.riot_game_name else None,
            "linked": player.puuid is not None,
        },
        "stats": asdict(s),
        "champions": sorted(
            ({"champion_id": c, "games": len(w), "wins": sum(w)} for c, w in champs.items()),
            key=lambda c: (-c["games"], -c["wins"], c["champion_id"]),
        ),
        "games": games[:60],
        "runs": runs,
        "items": dict(items),
        "gold_timeline": timeline,
        "tokens_earned": len(tokens),
    }
