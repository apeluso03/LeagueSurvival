"""In-app performance grade (SPEC 7.10). Riot's post-game grade isn't in Match-V5, so we make our own.

    score = 0.30 * kda_vs_team_avg
          + 0.25 * kill_participation
          + 0.25 * damage_share        (healing/shielding included for supports)
          + 0.20 * vision_vs_team_avg

Each part is 0..1 against the player's own team: for the "vs team average" parts, matching the
team average scores 0.5 and twice the average (or more) scores 1. Kill participation is already a
share. The thresholds below are first guesses to tune against real games (Open Question 9).
"""

GRADES = ["S+", "S", "S-", "A+", "A", "A-", "B+", "B", "B-", "C+", "C", "C-", "D"]
THRESHOLDS = [0.85, 0.78, 0.72, 0.66, 0.61, 0.56, 0.51, 0.46, 0.41, 0.36, 0.31, 0.26, 0.0]

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


def _vs_average(value: float, values: list[float]) -> float:
    avg = sum(values) / len(values) if values else 0
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
    team_kills = sum(x.get("kills", 0) for x in team)
    kp = min((p.get("kills", 0) + p.get("assists", 0)) / team_kills, 1.0) if team_kills else 0.0
    parts = {
        "kda": _vs_average(kda(p), [kda(x) for x in team]),
        "kp": kp,
        "damage": _vs_average(damage_with_support(p), [damage_with_support(x) for x in team]),
        "vision": _vs_average(p.get("visionScore", 0), [x.get("visionScore", 0) for x in team]),
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
