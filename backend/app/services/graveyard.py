"""The Graveyard (SPEC 21): every champion a run has lost, with how it lived and how it died.

One headstone per eliminated champion: who lost it and in which game, its last statline (Riot
stats, when the game has them), its record in the run, how many games it lived through, revives
and shields, and a one-line epitaph picked from those numbers. Plus the run's totals: who buried
the most, first blood, the quickest fall, the longest life, and the champions that came back.
"""

from collections import Counter
from dataclasses import asdict, dataclass, field

from sqlmodel import Session, col, select

from app.models import ChallengeGame, Champion, PlayerMatchStats, PoolEntry, PoolEvent, Run
from app.services.stats import run_champion_lines

TOP_GRADES = ("S+", "S", "S-")


@dataclass
class LastGame:
    kills: int
    deaths: int
    assists: int
    grade: str | None
    duration: int  # seconds
    team_position: str | None


@dataclass
class Headstone:
    champion_id: str
    name: str
    title: str
    tags: list[str]
    image_url: str
    eliminated_at: str | None
    game_id: int | None  # None: removed by hand
    player_id: int | None  # who was on it when it fell
    manual: bool
    last_game: LastGame | None
    offered: int
    played: int
    wins: int
    losses: int
    games_survived: int  # the run's finished games before the one it fell in
    deaths: int  # times eliminated in this run (more than 1 after a revive)
    revived: int
    shields_broken: int
    epitaph: str


@dataclass
class Risen:
    champion_id: str
    name: str
    image_url: str
    revived: int
    deaths: int


@dataclass
class Graveyard:
    run_id: int
    total: int
    dead: int
    headstones: list[Headstone] = field(default_factory=list)
    diggers: list[dict] = field(default_factory=list)  # [{"player_id", "count"}], most first
    by_class: list[dict] = field(default_factory=list)  # [{"tag", "count"}], most first
    first_blood: str | None = None  # champion ids
    quickest: str | None = None
    longest: str | None = None
    risen: list[Risen] = field(default_factory=list)


def epitaph(h: Headstone) -> str:
    """One line for the headstone, from the most telling number."""
    g = h.last_game
    if h.manual:
        return "Removed by hand. No last words."
    if h.played <= 1 and h.offered >= 4:
        return f"Offered {h.offered} times. Played once. Gone."
    if h.played <= 1:
        return "One game. That's all it got."
    if g and g.grade in TOP_GRADES:
        return f"Went down swinging: {g.grade} in its last game."
    if g and g.deaths >= 10:
        return f"Died {g.deaths} times in its last game. Then once more."
    if h.revived:
        return f"Came back {'once' if h.revived == 1 else f'{h.revived} times'}. Not this time."
    if h.shields_broken:
        return f"Outlived {h.shields_broken} shield{'s' if h.shields_broken > 1 else ''}. Not the last loss."
    if h.wins >= 3:
        return f"{h.wins} wins before the fall."
    if g and g.kills + g.assists == 0:
        return "Didn't touch a single kill on the way out."
    if h.games_survived >= 20:
        return f"Lived through {h.games_survived} games."
    return f"Fell in game {h.game_id}."


def build(session: Session, run: Run) -> Graveyard:
    entries = session.exec(
        select(PoolEntry, Champion).join(Champion, col(Champion.id) == col(PoolEntry.champion_id)).where(PoolEntry.run_id == run.id)
    ).all()
    lines = run_champion_lines(session, run.id)
    events = session.exec(select(PoolEvent).where(PoolEvent.run_id == run.id, col(PoolEvent.undone).is_(False))).all()
    deaths, revives, shields = Counter(), Counter(), Counter()
    for ev in events:
        if ev.type in ("eliminate", "manual_eliminate"):
            deaths[ev.champion_id] += 1
        elif ev.type in ("revive", "manual_revive"):
            revives[ev.champion_id] += 1
        elif ev.type == "shield_consumed":
            shields[ev.champion_id] += 1
    finished = session.exec(
        select(ChallengeGame).where(ChallengeGame.run_id == run.id, col(ChallengeGame.status).in_(["won", "lost"]))
    ).all()

    out = Graveyard(run_id=run.id, total=len(entries), dead=0)
    for entry, champ in entries:
        if entry.status != "eliminated":
            if revives[champ.id]:
                out.risen.append(Risen(champ.id, champ.name, champ.image_url, revives[champ.id], deaths[champ.id]))
            continue
        game_id = entry.eliminated_in_game_id
        last = None
        if game_id and entry.eliminated_by_player_id:
            pms = session.exec(
                select(PlayerMatchStats).where(
                    PlayerMatchStats.challenge_game_id == game_id, PlayerMatchStats.player_id == entry.eliminated_by_player_id
                )
            ).first()
            if pms:
                last = LastGame(pms.kills, pms.deaths, pms.assists, pms.rating_grade, pms.game_duration, pms.team_position or None)
        if game_id:
            survived = sum(1 for g in finished if g.id < game_id)
        else:
            survived = sum(1 for g in finished if g.resolved_at and entry.eliminated_at and g.resolved_at < entry.eliminated_at)
        line = lines.get(champ.id)
        h = Headstone(
            champion_id=champ.id,
            name=champ.name,
            title=champ.title,
            tags=list(champ.tags),
            image_url=champ.image_url,
            eliminated_at=entry.eliminated_at.isoformat() if entry.eliminated_at else None,
            game_id=game_id,
            player_id=entry.eliminated_by_player_id,
            manual=game_id is None,
            last_game=last,
            offered=line.offered if line else 0,
            played=line.played if line else 0,
            wins=line.wins if line else 0,
            losses=line.losses if line else 0,
            games_survived=survived,
            deaths=max(1, deaths[champ.id]),
            revived=revives[champ.id],
            shields_broken=shields[champ.id],
            epitaph="",
        )
        h.epitaph = epitaph(h)
        out.headstones.append(h)

    stones = out.headstones
    stones.sort(key=lambda h: h.eliminated_at or "", reverse=True)  # newest first
    out.dead = len(stones)
    out.risen.sort(key=lambda r: (-r.revived, r.name))
    diggers = Counter(h.player_id for h in stones if h.player_id is not None)
    out.diggers = [{"player_id": pid, "count": n} for pid, n in sorted(diggers.items(), key=lambda kv: (-kv[1], kv[0]))]
    classes = Counter(h.tags[0] for h in stones if h.tags)
    out.by_class = [{"tag": t, "count": n} for t, n in sorted(classes.items(), key=lambda kv: (-kv[1], kv[0]))]
    fallen = [h for h in stones if not h.manual]
    if fallen:
        oldest_first = sorted(fallen, key=lambda h: h.eliminated_at or "")
        out.first_blood = oldest_first[0].champion_id
        out.quickest = min(oldest_first, key=lambda h: h.games_survived).champion_id
        out.longest = max(oldest_first, key=lambda h: h.games_survived).champion_id
    return out


def to_dict(g: Graveyard) -> dict:
    return asdict(g)
