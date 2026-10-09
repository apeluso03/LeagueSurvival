"""Player stat calculations (SPEC 10.2).

A player's games are turned into `GameRecord`s from two sources:
- challenge games (won/lost) from the challenge tables, with Riot match stats when the game is linked;
- other imported Riot matches ("All tracked games" only), skipping remakes.
`compute` is pure; `player_stats` gathers the records from the database.
"""

from collections import defaultdict
from dataclasses import dataclass, field

from sqlmodel import Session, col, func, select

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
