"""Player stat calculations (SPEC 10.2).

A player's games are turned into `GameRecord`s from two sources:
- challenge games (won/lost) from the challenge tables, with Riot match stats when the game is linked;
- other imported Riot matches ("All tracked games" only), skipping remakes.
`compute` is pure; `player_stats` gathers the records from the database.
"""

from collections import defaultdict
from dataclasses import dataclass, field

from sqlmodel import Session, col, func, select

from app.services import economy, rating

from app.models import (
    AppSettings,
    ChallengeGame,
    Champion,
    PlayerMatchStats,
    PoolEvent,
    RiotMatch,
    SpinAssignment,
)

BEST_CHAMPION_MIN_GAMES = 2


@dataclass
class GameRecord:
    champion_id: str | None
    win: bool
    detail: PlayerMatchStats | None = None  # Riot stats, when available


@dataclass
class ChampionStats:
    champion_id: str
    games: int
    wins: int
    win_rate: float
    kda: float | None


@dataclass
class PlayerStats:
    player_id: int
    games: int = 0
    wins: int = 0
    losses: int = 0
    win_rate: float | None = None
    detailed_games: int = 0  # games with Riot stats behind the averages below
    avg_kills: float | None = None
    avg_deaths: float | None = None
    avg_assists: float | None = None
    kda: float | None = None
    kill_participation: float | None = None
    cs_per_min: float | None = None
    damage_per_min: float | None = None
    vision_per_min: float | None = None
    best_champions: list[ChampionStats] = field(default_factory=list)
    eliminated_champions: list[str] = field(default_factory=list)
    avg_grade: str | None = None  # average of the rating grades of games with Riot data
    gold_balance: int | None = None  # gold fields only when a single run is selected
    gold_earned: int | None = None
    gold_spent: int | None = None


def kda(kills: int, deaths: int, assists: int) -> float:
    return (kills + assists) / max(deaths, 1)


def kill_participation(kills: int, assists: int, team_kills: int) -> float | None:
    return (kills + assists) / team_kills if team_kills > 0 else None


def _per_min(total: int, seconds: int) -> float | None:
    return total / (seconds / 60) if seconds > 0 else None


def compute(player_id: int, records: list[GameRecord]) -> PlayerStats:
    s = PlayerStats(player_id=player_id, games=len(records))
    s.wins = sum(r.win for r in records)
    s.losses = s.games - s.wins
    s.win_rate = s.wins / s.games if s.games else None

    details = [r.detail for r in records if r.detail is not None]
    s.detailed_games = len(details)
    if details:
        n = len(details)
        k = sum(d.kills for d in details)
        d_ = sum(d.deaths for d in details)
        a = sum(d.assists for d in details)
        secs = sum(d.game_duration for d in details)
        s.avg_kills, s.avg_deaths, s.avg_assists = k / n, d_ / n, a / n
        s.kda = kda(k, d_, a)
        s.kill_participation = kill_participation(k, a, sum(d.team_kills for d in details))
        s.cs_per_min = _per_min(sum(d.cs for d in details), secs)
        s.damage_per_min = _per_min(sum(d.damage_to_champs for d in details), secs)
        s.vision_per_min = _per_min(sum(d.vision_score for d in details), secs)
        graded = [rating.GRADES.index(d.rating_grade) for d in details if d.rating_grade in rating.GRADES]
        if graded:
            s.avg_grade = rating.GRADES[round(sum(graded) / len(graded))]

    by_champ: dict[str, list[GameRecord]] = defaultdict(list)
    for r in records:
        if r.champion_id:
            by_champ[r.champion_id].append(r)
    best = []
    for cid, recs in by_champ.items():
        if len(recs) < BEST_CHAMPION_MIN_GAMES:
            continue
        wins = sum(r.win for r in recs)
        ds = [r.detail for r in recs if r.detail]
        champ_kda = (
            kda(sum(d.kills for d in ds), sum(d.deaths for d in ds), sum(d.assists for d in ds)) if ds else None
        )
        best.append(ChampionStats(cid, len(recs), wins, wins / len(recs), champ_kda))
    best.sort(key=lambda c: (c.win_rate, c.kda if c.kda is not None else -1, c.games), reverse=True)
    s.best_champions = best
    return s


# --- gathering from the database ------------------------------------------------


def _is_remake(match: RiotMatch, threshold_seconds: int) -> bool:
    return match.early_surrender or match.game_duration < threshold_seconds


def gather_records(
    session: Session, player_ids: list[int], run_id: int | None, challenge_only: bool
) -> dict[int, list[GameRecord]]:
    records: dict[int, list[GameRecord]] = {pid: [] for pid in player_ids}
    champ_by_key = {c.key: c.id for c in session.exec(select(Champion)).all()}

    games_q = select(ChallengeGame, SpinAssignment).join(
        SpinAssignment, col(SpinAssignment.game_id) == col(ChallengeGame.id)
    ).where(col(ChallengeGame.status).in_(["won", "lost"]), col(SpinAssignment.player_id).in_(player_ids))
    if run_id is not None:
        games_q = games_q.where(ChallengeGame.run_id == run_id)
    for game, a in session.exec(games_q).all():
        detail = session.get(PlayerMatchStats, (game.riot_match_id, a.player_id)) if game.riot_match_id else None
        records[a.player_id].append(GameRecord(a.played_champion_id, game.status == "won", detail))

    if not challenge_only:
        settings = session.get(AppSettings, 1) or AppSettings()
        rows = session.exec(
            select(PlayerMatchStats, RiotMatch)
            .join(RiotMatch, col(RiotMatch.match_id) == col(PlayerMatchStats.match_id))
            .where(col(PlayerMatchStats.player_id).in_(player_ids), col(PlayerMatchStats.is_challenge).is_(False))
        ).all()
        for pms, match in rows:
            if _is_remake(match, settings.remake_threshold_seconds):
                continue
            records[pms.player_id].append(GameRecord(champ_by_key.get(pms.champion_key), pms.win, pms))
    return records


def eliminated_by(session: Session, player_ids: list[int], run_id: int | None) -> dict[int, list[str]]:
    q = select(PoolEvent).where(
        PoolEvent.type == "eliminate", col(PoolEvent.undone).is_(False), col(PoolEvent.player_id).in_(player_ids)
    )
    if run_id is not None:
        q = q.where(PoolEvent.run_id == run_id)
    out: dict[int, list[str]] = {pid: [] for pid in player_ids}
    for ev in session.exec(q.order_by(col(PoolEvent.id))).all():
        out[ev.player_id].append(ev.champion_id)
    return out


def player_stats(
    session: Session, player_ids: list[int], run_id: int | None = None, challenge_only: bool = True
) -> list[PlayerStats]:
    records = gather_records(session, player_ids, run_id, challenge_only)
    eliminated = eliminated_by(session, player_ids, run_id)
    result = []
    for pid in player_ids:
        s = compute(pid, records[pid])
        s.eliminated_champions = eliminated[pid]
        if run_id is not None:
            t = economy.totals(session, run_id, pid)
            s.gold_balance, s.gold_earned, s.gold_spent = t["balance"], t["earned"], t["spent"]
        result.append(s)
    return result


# --- one champion (Pool tab card, SPEC 17.4) ---------------------------------------------


@dataclass
class PlayerChampionLine:
    player_id: int
    games: int
    wins: int


@dataclass
class ChampionReport:
    champion_id: str
    # This run
    in_run: bool = False
    status: str | None = None  # "alive" | "eliminated"
    eliminated_at: object = None
    eliminated_by_player_id: int | None = None
    eliminated_in_game_id: int | None = None
    times_offered: int = 0
    times_played: int = 0
    wins: int = 0
    losses: int = 0
    played_by: list[PlayerChampionLine] = field(default_factory=list)
    # Every run
    all_runs_played: int = 0
    all_runs_wins: int = 0
    # Imported Riot matches for the group (remakes skipped)
    riot_games: int = 0
    riot_wins: int = 0
    riot_kda: float | None = None
    riot_players: list[PlayerChampionLine] = field(default_factory=list)


def _lines(rows: list[tuple[int, bool]]) -> list[PlayerChampionLine]:
    by: dict[int, list[bool]] = defaultdict(list)
    for pid, win in rows:
        by[pid].append(win)
    lines = [PlayerChampionLine(pid, len(w), sum(w)) for pid, w in by.items()]
    return sorted(lines, key=lambda line: (-line.games, -line.wins))


def champion_report(session: Session, champion: Champion, run_id: int | None) -> ChampionReport:
    from app.models import PoolEntry  # local: only needed here

    rep = ChampionReport(champion_id=champion.id)

    played = session.exec(
        select(SpinAssignment, ChallengeGame)
        .join(ChallengeGame, col(ChallengeGame.id) == col(SpinAssignment.game_id))
        .where(SpinAssignment.played_champion_id == champion.id, col(ChallengeGame.status).in_(["won", "lost"]))
    ).all()
    rep.all_runs_played = len(played)
    rep.all_runs_wins = sum(g.status == "won" for _, g in played)

    if run_id is not None:
        entry = session.get(PoolEntry, (run_id, champion.id))
        if entry:
            rep.in_run = True
            rep.status = entry.status
            rep.eliminated_at = entry.eliminated_at
            rep.eliminated_by_player_id = entry.eliminated_by_player_id
            rep.eliminated_in_game_id = entry.eliminated_in_game_id
        run_played = [(a, g) for a, g in played if g.run_id == run_id]
        rep.times_played = len(run_played)
        rep.wins = sum(g.status == "won" for _, g in run_played)
        rep.losses = rep.times_played - rep.wins
        rep.played_by = _lines([(a.player_id, g.status == "won") for a, g in run_played])
        offers = session.exec(
            select(SpinAssignment.options)
            .join(ChallengeGame, col(ChallengeGame.id) == col(SpinAssignment.game_id))
            # Re-rolled spins don't count as offers (NULL-safe: most games have no void reason)
            .where(ChallengeGame.run_id == run_id, func.coalesce(ChallengeGame.void_reason, "") != "re-roll")
        ).all()
        rep.times_offered = sum(champion.id in opts for opts in offers)

    settings = session.get(AppSettings, 1) or AppSettings()
    riot = [
        pms
        for pms, match in session.exec(
            select(PlayerMatchStats, RiotMatch)
            .join(RiotMatch, col(RiotMatch.match_id) == col(PlayerMatchStats.match_id))
            .where(PlayerMatchStats.champion_key == champion.key)
        ).all()
        if not _is_remake(match, settings.remake_threshold_seconds)
    ]
    rep.riot_games = len(riot)
    rep.riot_wins = sum(r.win for r in riot)
    if riot:
        rep.riot_kda = kda(sum(r.kills for r in riot), sum(r.deaths for r in riot), sum(r.assists for r in riot))
    rep.riot_players = _lines([(r.player_id, r.win) for r in riot])
    return rep


@dataclass
class ChampionLine:
    """A champion's short numbers for one run, shown on its Pool card."""

    offered: int = 0
    played: int = 0
    wins: int = 0
    losses: int = 0
    on_spin: list[int] = field(default_factory=list)  # players with it in the pending spin's options
    blacklisted_by: list[int] = field(default_factory=list)  # players with it on an armed blacklist


def run_champion_lines(session: Session, run_id: int) -> dict[str, ChampionLine]:
    """Every champion's Pool-card numbers for a run in one go. Champions with nothing to show are left out."""
    from app.models import InventoryItem  # local: only needed here

    lines: dict[str, ChampionLine] = defaultdict(ChampionLine)
    rows = session.exec(
        select(SpinAssignment, ChallengeGame)
        .join(ChallengeGame, col(ChallengeGame.id) == col(SpinAssignment.game_id))
        .where(ChallengeGame.run_id == run_id, func.coalesce(ChallengeGame.void_reason, "") != "re-roll")
    ).all()
    for a, g in rows:
        for cid in a.options:
            lines[cid].offered += 1
            if g.status == "pending":
                lines[cid].on_spin.append(a.player_id)
        if a.played_champion_id and g.status in ("won", "lost"):
            line = lines[a.played_champion_id]
            line.played += 1
            if g.status == "won":
                line.wins += 1
            else:
                line.losses += 1
    armed = session.exec(
        select(InventoryItem).where(
            InventoryItem.run_id == run_id, InventoryItem.type == "blacklist", InventoryItem.status == "armed"
        )
    ).all()
    for item in armed:
        for cid in item.target.get("champion_ids", []):
            lines[cid].blacklisted_by.append(item.player_id)
    return dict(lines)


# --- option facts (Wheels tab: short numbers under each rolled champion) ----------------------


@dataclass
class OptionFact:
    you_games: int = 0  # this player's challenge games on the champion (every run)
    you_wins: int = 0
    riot_games: int = 0  # this player's imported Riot games on it (remakes skipped)
    riot_wins: int = 0
    group_games: int = 0  # everyone's challenge games on it (every run)
    group_wins: int = 0


def option_facts(session: Session, game: ChallengeGame) -> dict[int, dict[str, OptionFact]]:
    """For every player in a game, a fact line for each champion in their options."""
    assignments = session.exec(select(SpinAssignment).where(SpinAssignment.game_id == game.id)).all()
    champ_ids = {c for a in assignments for c in a.options}
    if not champ_ids:
        return {}
    key_of = {c.id: c.key for c in session.exec(select(Champion).where(col(Champion.id).in_(champ_ids))).all()}
    id_of = {k: c for c, k in key_of.items()}

    played = session.exec(
        select(SpinAssignment.player_id, SpinAssignment.played_champion_id, ChallengeGame.status)
        .join(ChallengeGame, col(ChallengeGame.id) == col(SpinAssignment.game_id))
        .where(col(SpinAssignment.played_champion_id).in_(champ_ids), col(ChallengeGame.status).in_(["won", "lost"]))
    ).all()
    settings = session.get(AppSettings, 1) or AppSettings()
    riot = [
        pms
        for pms, match in session.exec(
            select(PlayerMatchStats, RiotMatch)
            .join(RiotMatch, col(RiotMatch.match_id) == col(PlayerMatchStats.match_id))
            .where(col(PlayerMatchStats.champion_key).in_(list(id_of)))
        ).all()
        if not _is_remake(match, settings.remake_threshold_seconds)
    ]

    out: dict[int, dict[str, OptionFact]] = {}
    for a in assignments:
        facts = {c: OptionFact() for c in a.options}
        for pid, cid, status in played:
            f = facts.get(cid)
            if f is None:
                continue
            won = status == "won"
            f.group_games += 1
            f.group_wins += won
            if pid == a.player_id:
                f.you_games += 1
                f.you_wins += won
        for pms in riot:
            f = facts.get(id_of.get(pms.champion_key, ""))
            if f is not None and pms.player_id == a.player_id:
                f.riot_games += 1
                f.riot_wins += pms.win
        out[a.player_id] = facts
    return out
