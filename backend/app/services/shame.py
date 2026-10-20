"""Hall of Shame and monthly Wrapped: the fun read-only summaries."""

from collections import Counter, defaultdict
from datetime import UTC, datetime
from itertools import combinations

from sqlmodel import Session, col, select

from app.models import (
    ChallengeGame,
    Champion,
    GoldLedger,
    InventoryItem,
    PlayerMatchStats,
    PoolEvent,
    SpinAssignment,
)
from app.services.stats import kda

TOP = 8


def _group_runs(group_id: int):
    from app.models import Run

    return select(Run.id).where(Run.group_id == group_id)


def _challenge_rows(
    session: Session, group_id: int, run_id: int | None = None, since: datetime | None = None, until: datetime | None = None
):
    q = (
        select(SpinAssignment, ChallengeGame)
        .join(ChallengeGame, col(ChallengeGame.id) == col(SpinAssignment.game_id))
        .where(col(ChallengeGame.status).in_(["won", "lost"]), col(ChallengeGame.run_id).in_(_group_runs(group_id)))
        .order_by(col(ChallengeGame.id))
    )
    if run_id is not None:
        q = q.where(ChallengeGame.run_id == run_id)
    if since is not None:
        q = q.where(ChallengeGame.created_at >= since)
    if until is not None:
        q = q.where(ChallengeGame.created_at < until)
    return session.exec(q).all()


def _game_line(a: SpinAssignment, g: ChallengeGame, pms: PlayerMatchStats | None, champ_by_key: dict[int, str]) -> dict:
    champ = a.played_champion_id or (champ_by_key.get(pms.champion_key) if pms else None)
    return {
        "game_id": g.id,
        "run_id": g.run_id,
        "player_id": a.player_id,
        "champion_id": champ,
        "won": g.status == "won",
        "kills": pms.kills if pms else None,
        "deaths": pms.deaths if pms else None,
        "assists": pms.assists if pms else None,
        "kda": kda(pms.kills, pms.deaths, pms.assists) if pms else None,
        "duration": pms.game_duration if pms else None,
        "at": g.created_at,
    }


def hall_of_shame(session: Session, group_id: int, run_id: int | None = None) -> dict:
    champ_by_key = {c.key: c.id for c in session.exec(select(Champion)).all()}
    rows = _challenge_rows(session, group_id, run_id)
    lines = []
    for a, g in rows:
        pms = session.get(PlayerMatchStats, (g.riot_match_id, a.player_id)) if g.riot_match_id else None
        lines.append(_game_line(a, g, pms, champ_by_key))
    detailed = [x for x in lines if x["kda"] is not None]

    # Champions the group keeps losing on (2+ games, losing record), worst win rate first.
    by_champ: dict[str, list[bool]] = defaultdict(list)
    for x in lines:
        if x["champion_id"]:
            by_champ[x["champion_id"]].append(x["won"])
    cursed = sorted(
        ({"champion_id": c, "games": len(w), "wins": sum(w)} for c, w in by_champ.items() if len(w) >= 2 and sum(w) * 2 < len(w)),
        key=lambda c: (c["wins"] / c["games"], -c["games"]),
    )[:TOP]

    deaths: dict[int, list[int]] = defaultdict(list)
    for x in detailed:
        deaths[x["player_id"]].append(x["deaths"])
    feeders = sorted(
        (
            {"player_id": pid, "games": len(d), "deaths": sum(d), "avg_deaths": sum(d) / len(d)}
            for pid, d in deaths.items()
        ),
        key=lambda f: -f["avg_deaths"],
    )

    elim_q = select(PoolEvent).where(
        PoolEvent.type == "eliminate", col(PoolEvent.undone).is_(False), col(PoolEvent.run_id).in_(_group_runs(group_id))
    )
    if run_id is not None:
        elim_q = elim_q.where(PoolEvent.run_id == run_id)
    reapers = Counter(e.player_id for e in session.exec(elim_q).all() if e.player_id is not None)

    # Rerolls (and other spin items) used in games that were lost anyway.
    item_q = select(InventoryItem, ChallengeGame).join(
        ChallengeGame, col(ChallengeGame.id) == col(InventoryItem.used_in_game_id)
    ).where(
        col(InventoryItem.type).in_(["reroll", "swap", "choose"]),
        ChallengeGame.status == "lost",
        col(ChallengeGame.run_id).in_(_group_runs(group_id)),
    )
    if run_id is not None:
        item_q = item_q.where(ChallengeGame.run_id == run_id)
    wasted: dict[int, dict] = {}
    for item, _ in session.exec(item_q).all():
        w = wasted.setdefault(item.player_id, {"player_id": item.player_id, "items": 0, "gold": 0})
        w["items"] += 1
        w["gold"] += item.price_paid

    losses = [x for x in detailed if not x["won"] and x["duration"]]
    return {
        "worst_games": sorted(detailed, key=lambda x: (x["kda"], -x["deaths"]))[:TOP],
        "most_deaths": sorted(detailed, key=lambda x: -x["deaths"])[:5],
        "fastest_losses": sorted(losses, key=lambda x: x["duration"])[:5],
        "cursed_champions": cursed,
        "feeders": feeders,
        "reapers": [{"player_id": pid, "champions_lost": n} for pid, n in reapers.most_common()],
        "wasted_items": sorted(wasted.values(), key=lambda w: -w["gold"]),
    }


# --- monthly Wrapped -----------------------------------------------------------------------


def month_bounds(month: str) -> tuple[datetime, datetime]:
    year, mon = (int(x) for x in month.split("-"))
    start = datetime(year, mon, 1, tzinfo=UTC)
    end = datetime(year + (mon == 12), 1 if mon == 12 else mon + 1, 1, tzinfo=UTC)
    return start, end


def available_months(session: Session, group_id: int) -> list[str]:
    dates = session.exec(
        select(ChallengeGame.created_at).where(
            col(ChallengeGame.status).in_(["won", "lost"]), col(ChallengeGame.run_id).in_(_group_runs(group_id))
        )
    ).all()
    return sorted({d.strftime("%Y-%m") for d in dates if d}, reverse=True)


def wrapped(session: Session, month: str, group_id: int) -> dict:
    start, end = month_bounds(month)
    champ_by_key = {c.key: c.id for c in session.exec(select(Champion)).all()}
    rows = _challenge_rows(session, group_id, since=start, until=end)
    games: dict[int, ChallengeGame] = {}
    players: dict[int, dict] = {}
    champs: Counter = Counter()
    champ_wins: Counter = Counter()
    by_game: dict[int, list[int]] = defaultdict(list)
    lines = []
    for a, g in rows:
        games[g.id] = g
        by_game[g.id].append(a.player_id)
        pms = session.get(PlayerMatchStats, (g.riot_match_id, a.player_id)) if g.riot_match_id else None
        line = _game_line(a, g, pms, champ_by_key)
        lines.append(line)
        p = players.setdefault(
            a.player_id,
            {"player_id": a.player_id, "games": 0, "wins": 0, "kills": 0, "deaths": 0, "assists": 0, "detailed": 0,
             "champions": Counter(), "pentas": 0},
        )
        p["games"] += 1
        p["wins"] += line["won"]
        if line["champion_id"]:
            p["champions"][line["champion_id"]] += 1
            champs[line["champion_id"]] += 1
            champ_wins[line["champion_id"]] += line["won"]
        if pms:
            p["detailed"] += 1
            p["kills"] += pms.kills
            p["deaths"] += pms.deaths
            p["assists"] += pms.assists
            p["pentas"] += pms.penta_kills

    ordered = sorted(games.values(), key=lambda g: g.id)
    best_streak = streak = 0
    for g in ordered:
        streak = streak + 1 if g.status == "won" else 0
        best_streak = max(best_streak, streak)

    duos: dict[tuple[int, int], list[bool]] = defaultdict(list)
    for gid, pids in by_game.items():
        for a, b in combinations(sorted(set(pids)), 2):
            duos[(a, b)].append(games[gid].status == "won")
    duo_list = [{"players": list(k), "games": len(v), "wins": sum(v)} for k, v in duos.items() if len(v) >= 2]
    best_duo = max(duo_list, key=lambda d: (d["wins"] / d["games"], d["games"]), default=None)
    worst_duo = min(duo_list, key=lambda d: (d["wins"] / d["games"], -d["games"]), default=None)

    elims = session.exec(
        select(PoolEvent).where(
            PoolEvent.type == "eliminate",
            col(PoolEvent.undone).is_(False),
            PoolEvent.created_at >= start,
            PoolEvent.created_at < end,
            col(PoolEvent.run_id).in_(_group_runs(group_id)),
        )
    ).all()
    spend = session.exec(
        select(GoldLedger, InventoryItem)
        .join(InventoryItem, col(InventoryItem.id) == col(GoldLedger.item_id))
        .where(
            GoldLedger.reason == "purchase",
            col(GoldLedger.undone).is_(False),
            GoldLedger.created_at >= start,
            GoldLedger.created_at < end,
            col(GoldLedger.run_id).in_(_group_runs(group_id)),
        )
    ).all()
    spent_by: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for row, item in spend:
        spent_by[row.player_id][item.type] -= row.amount

    def player_out(p: dict) -> dict:
        top = p["champions"].most_common(1)
        return {
            "player_id": p["player_id"],
            "games": p["games"],
            "wins": p["wins"],
            "kda": kda(p["kills"], p["deaths"], p["assists"]) if p["detailed"] else None,
            "kills": p["kills"] if p["detailed"] else None,
            "deaths": p["deaths"] if p["detailed"] else None,
            "avg_deaths": p["deaths"] / p["detailed"] if p["detailed"] else None,
            "pentas": p["pentas"],
            "top_champion": top[0][0] if top else None,
            "top_champion_games": top[0][1] if top else 0,
            "champions_lost": sum(1 for e in elims if e.player_id == p["player_id"]),
            "gold_spent": sum(spent_by[p["player_id"]].values()),
            "reroll_gold": spent_by[p["player_id"]].get("reroll", 0),
        }

    plist = sorted((player_out(p) for p in players.values()), key=lambda p: (-p["wins"], -p["games"]))
    floor = max((p["games"] for p in plist), default=0) / 2
    mvp = max((p for p in plist if p["games"] >= floor and p["games"]), key=lambda p: (p["wins"] / p["games"], p["games"]), default=None)
    with_riot = [p for p in plist if p["avg_deaths"] is not None]
    detailed = [x for x in lines if x["kda"] is not None]
    most_played = champs.most_common(1)
    return {
        "month": month,
        "months": available_months(session, group_id),
        "games": len(games),
        "wins": sum(g.status == "won" for g in games.values()),
        "best_streak": best_streak,
        "champions_lost": len(elims),
        "gold_spent": sum(sum(v.values()) for v in spent_by.values()),
        "reroll_gold": sum(v.get("reroll", 0) for v in spent_by.values()),
        "items_bought": len(spend),
        "pentas": sum(p["pentas"] for p in plist),
        "most_played": {"champion_id": most_played[0][0], "games": most_played[0][1], "wins": champ_wins[most_played[0][0]]}
        if most_played
        else None,
        "mvp": mvp,
        "feeder": max(with_riot, key=lambda p: p["avg_deaths"], default=None),
        "top_killer": max(with_riot, key=lambda p: p["kills"], default=None),
        "best_duo": best_duo,
        "worst_duo": worst_duo if worst_duo is not best_duo else None,
        "worst_game": min(detailed, key=lambda x: (x["kda"], -x["deaths"]), default=None),
        "best_game": max(detailed, key=lambda x: (x["kda"], x["kills"]), default=None),
        "players": plist,
    }
