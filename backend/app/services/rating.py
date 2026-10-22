"""In-app performance grade (SPEC 7.10). Riot's post-game grade isn't in Match-V5, so we make our own.

    score = 0.30 * kda_vs_team_avg
          + 0.25 * kill_participation
          + 0.25 * damage_share        (healing/shielding included for supports)
          + 0.20 * vision_vs_team_avg

Each part is 0..1 against the player's teammates: for the "vs teammates" parts, matching their
average scores 0.5 and twice it (or more) scores 1. The player isn't in that average: counting
yourself pulls the average toward you, and made a top grade nearly impossible (a game twice as good
as your teammates' only scored about 0.8 of the way). Kill participation is already a share.

THRESHOLDS come from 990 real 5v5 player-games (2026-10), set so about the top 2% get S+, 6% S or
better, 12% S- or better and 20% A+ or better, near how often the client hands out S grades.
Changing them? Regrade stored games with a migration, like f8b2d4c6a9e1.
"""

GRADES = ["S+", "S", "S-", "A+", "A", "A-", "B+", "B", "B-", "C+", "C", "C-", "D"]
THRESHOLDS = [0.82, 0.75, 0.71, 0.64, 0.58, 0.54, 0.50, 0.45, 0.40, 0.35, 0.30, 0.25, 0.0]

WEIGHTS = {"kda": 0.30, "kp": 0.25, "damage": 0.25, "vision": 0.20}


def grade_for(score: float) -> str:
    for grade, floor in zip(GRADES, THRESHOLDS):
        if score >= floor:
            return grade
    return GRADES[-1]


def at_least(grade: str | None, target: str) -> bool:
    """True if `grade` is `target` or better (S+ is best)."""
    if grade not in GRADES or target not in GRADES:
        return False
    return GRADES.index(grade) <= GRADES.index(target)


def _vs_others(value: float, others: list[float]) -> float:
    """0.5 for matching the teammates' average, 1 for twice it or more."""
    avg = sum(others) / len(others) if others else 0
    if avg <= 0:
        return 0.5 if value <= 0 else 1.0
    return min(value / avg / 2, 1.0)


def damage_with_support(p: dict) -> int:
    dmg = p.get("totalDamageDealtToChampions", 0)
    if p.get("teamPosition") == "UTILITY":
        dmg += p.get("totalHealsOnTeammates", 0) + p.get("totalDamageShieldedOnTeammates", 0)
    return dmg


def score_participant(p: dict, team: list[dict]) -> float:
    kda = lambda x: (x.get("kills", 0) + x.get("assists", 0)) / max(x.get("deaths", 0), 1)  # noqa: E731
    others = [x for x in team if x is not p]
    team_kills = sum(x.get("kills", 0) for x in team)
    kp = min((p.get("kills", 0) + p.get("assists", 0)) / team_kills, 1.0) if team_kills else 0.0
    parts = {
        "kda": _vs_others(kda(p), [kda(x) for x in others]),
        "kp": kp,
        "damage": _vs_others(damage_with_support(p), [damage_with_support(x) for x in others]),
        "vision": _vs_others(p.get("visionScore", 0), [x.get("visionScore", 0) for x in others]),
    }
    return sum(WEIGHTS[k] * v for k, v in parts.items())


def grades_for_match(raw: dict) -> dict[str, str]:
    """Grade for every participant in a Match-V5 response, keyed by puuid."""
    participants = raw.get("info", {}).get("participants", [])
    out = {}
    for p in participants:
        team = [x for x in participants if x.get("teamId") == p.get("teamId")]
        if p.get("puuid"):
            out[p["puuid"]] = grade_for(score_participant(p, team))
    return out
