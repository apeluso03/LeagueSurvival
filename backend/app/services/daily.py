"""Daily Statline (SPEC 20): a daily guessing game built from a group's own run history.

Each day (midnight in config.daily_timezone) a group gets one puzzle: one player's statline from
a past challenge game with Riot stats, picked at random from the lines never used before. The
other players' lines from that game stay available for later days.

The clue is the champion, role, game length and queue. Four questions, in order:

    result   Win or loss?                1 try     1 point
    pilot    Who was piloting?           2 tries   2 / 1 points
    kda      Kills / deaths / assists    4 tries   4 / 3 / 2 / 1 points (higher/lower per number)
    grade    The grade (S+ to D)         3 tries   3 / 2 / 1 points (higher/lower)

The grade question is left out for a game without one. Everyone in the group plays the same
puzzle once per day, on the site or through the Discord bot (the same guesses either way).
"""

import random
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col, select

from app.config import get_settings
from app.models import (
    ChallengeGame,
    Champion,
    DailyPlay,
    DailyPuzzle,
    GroupMember,
    Player,
    PlayerMatchStats,
    RiotMatch,
    Run,
    User,
    utcnow,
)
from app.services import rating
from app.services.rules import RuleError

QUESTIONS = ("result", "pilot", "kda", "grade")
POINTS = {"result": [1], "pilot": [2, 1], "kda": [4, 3, 2, 1], "grade": [3, 2, 1]}
LABELS = {"result": "Win or loss?", "pilot": "Who was piloting?", "kda": "K / D / A", "grade": "Grade"}
CLOSE = 2  # a K/D/A number within this of the answer counts as close


def today(now: datetime | None = None) -> str:
    tz = ZoneInfo(get_settings().daily_timezone)
    return (now or datetime.now(UTC)).astimezone(tz).date().isoformat()


def _previous(day: str) -> str:
    return (date.fromisoformat(day) - timedelta(days=1)).isoformat()


# --- picking the puzzle ---------------------------------------------------------------------------


def candidates(session: Session, group_id: int) -> list[PlayerMatchStats]:
    """Statlines a puzzle can use: the group's players in finished challenge games with Riot stats,
    minus the ones already used."""
    rows = session.exec(
        select(PlayerMatchStats)
        .join(ChallengeGame, col(ChallengeGame.id) == col(PlayerMatchStats.challenge_game_id))
        .join(Run, col(Run.id) == col(ChallengeGame.run_id))
        .join(Player, col(Player.id) == col(PlayerMatchStats.player_id))
        .where(
            Run.group_id == group_id,
            Player.group_id == group_id,
            col(PlayerMatchStats.is_challenge).is_(True),
            col(ChallengeGame.status).in_(["won", "lost"]),
        )
        .order_by(col(PlayerMatchStats.match_id), col(PlayerMatchStats.player_id))
    ).all()
    used = {(p.match_id, p.player_id) for p in session.exec(select(DailyPuzzle).where(DailyPuzzle.group_id == group_id)).all()}
    return [r for r in rows if (r.match_id, r.player_id) not in used]


def puzzle_for(
    session: Session, group_id: int, day: str | None = None, create: bool = True, rng: random.Random | None = None
) -> DailyPuzzle | None:
    """The group's puzzle for `day` (today by default), made on first use. None when the group has
    no statline left to use (no finished challenge games with Riot stats yet, or all used)."""
    day = day or today()
    existing = session.exec(select(DailyPuzzle).where(DailyPuzzle.group_id == group_id, DailyPuzzle.day == day)).first()
    if existing or not create:
        return existing
    pool = candidates(session, group_id)
    if not pool:
        return None
    pick = (rng or random.SystemRandom()).choice(pool)
    number = len(session.exec(select(DailyPuzzle.id).where(DailyPuzzle.group_id == group_id)).all()) + 1
    puzzle = DailyPuzzle(
        group_id=group_id, day=day, number=number, match_id=pick.match_id, player_id=pick.player_id, game_id=pick.challenge_game_id
    )
    try:
        with session.begin_nested():  # two people opening it at the same moment: one wins
            session.add(puzzle)
    except IntegrityError:
        return session.exec(select(DailyPuzzle).where(DailyPuzzle.group_id == group_id, DailyPuzzle.day == day)).first()
    return puzzle


# --- the answer and the guesses ------------------------------------------------------------------


def answer(session: Session, puzzle: DailyPuzzle) -> dict:
    pms = session.get(PlayerMatchStats, (puzzle.match_id, puzzle.player_id))
    champ = session.exec(select(Champion).where(Champion.key == pms.champion_key)).first()
    match = session.get(RiotMatch, puzzle.match_id)
    return {
        "result": "win" if pms.win else "loss",
        "pilot": pms.player_id,
        "kda": [pms.kills, pms.deaths, pms.assists],
        "grade": pms.rating_grade,
        "champion_id": champ.id if champ else None,
        "role": pms.team_position or None,
        "duration": match.game_duration if match else pms.game_duration,
        "queue_id": match.queue_id if match else pms.queue_id,
        "played_at": match.game_start if match else None,
        "game_id": puzzle.game_id,
    }


def questions(ans: dict) -> list[str]:
    return [q for q in QUESTIONS if q != "grade" or ans["grade"] in rating.GRADES]


def max_score(ans: dict) -> int:
    return sum(POINTS[q][0] for q in questions(ans))


def _check(q: str, guess, ans: dict) -> dict:
    """How one guess compares with the answer."""
    if q == "kda":
        parts = []
        for g, a in zip(guess, ans["kda"], strict=True):
            hint = "exact" if g == a else ("higher" if a > g else "lower")  # the answer is higher/lower
            parts.append({"value": g, "hint": hint, "close": hint != "exact" and abs(a - g) <= CLOSE})
        return {"value": guess, "correct": all(p["hint"] == "exact" for p in parts), "parts": parts}
    if q == "grade":
        gi, ai = rating.GRADES.index(guess), rating.GRADES.index(ans["grade"])
        hint = "exact" if gi == ai else ("higher" if ai < gi else "lower")  # higher = a better grade
        return {"value": guess, "correct": gi == ai, "hint": hint, "close": abs(gi - ai) == 1}
    return {"value": guess, "correct": guess == ans[q]}


def progress(play: DailyPlay | None, ans: dict) -> dict:
    """Every question's guesses with their feedback, which one is up, and the score so far."""
    guesses = (play.guesses if play else {}) or {}
    out, current, score = [], None, 0
    for q in questions(ans):
        tries = len(POINTS[q])
        checked = [_check(q, g, ans) for g in guesses.get(q, [])]
        solved = any(c["correct"] for c in checked)
        finished = solved or len(checked) >= tries
        points = POINTS[q][len(checked) - 1] if solved else 0
        score += points
        if not finished and current is None:
            current = q
        out.append(
            {"id": q, "label": LABELS[q], "tries": tries, "guesses": checked, "solved": solved, "finished": finished, "points": points}
        )
    return {"questions": out, "current": current, "done": current is None, "score": score, "max_score": max_score(ans)}


def _group_players(session: Session, group_id: int) -> list[Player]:
    return list(session.exec(select(Player).where(Player.group_id == group_id).order_by(col(Player.display_name))).all())


def _normalize(session: Session, puzzle: DailyPuzzle, q: str, value):
    if q == "result":
        if value not in ("win", "loss"):
            raise RuleError("Guess win or loss")
        return value
    if q == "pilot":
        try:
            pid = int(value)
        except (TypeError, ValueError):
            raise RuleError("Pick a player") from None
        if pid not in {p.id for p in _group_players(session, puzzle.group_id)}:
            raise RuleError("Pick a player in your group")
        return pid
    if q == "kda":
        try:
            nums = [int(v) for v in value]
        except (TypeError, ValueError):
            raise RuleError("Kills, deaths and assists are whole numbers") from None
        if len(nums) != 3 or any(not 0 <= n <= 99 for n in nums):
            raise RuleError("Guess kills, deaths and assists, each 0 to 99")
        return nums
    if value not in rating.GRADES:
        raise RuleError(f"Pick a grade: {', '.join(rating.GRADES)}")
    return value


def guess(session: Session, puzzle: DailyPuzzle, user: User, q: str, value) -> DailyPlay:
    """Record one guess for the question that's up. Questions go in order; each ends when it's
    right or out of tries."""
    if puzzle.day != today():
        raise RuleError("That puzzle is over. Play today's.", 409)
    ans = answer(session, puzzle)
    play = session.exec(select(DailyPlay).where(DailyPlay.puzzle_id == puzzle.id, DailyPlay.user_id == user.id)).first()
    state = progress(play, ans)
    if state["done"]:
        raise RuleError("You've already played today's puzzle. Come back tomorrow.", 409)
    if q != state["current"]:
        raise RuleError(f"Answer \"{LABELS[state['current']]}\" first.", 409)
    value = _normalize(session, puzzle, q, value)
    if play is None:
        play = DailyPlay(puzzle_id=puzzle.id, user_id=user.id)
    previous = list(play.guesses.get(q, []))
    if value in previous:
        raise RuleError("You already guessed that.", 409)
    play.guesses = {**play.guesses, q: [*previous, value]}
    state = progress(play, ans)
    play.score = state["score"]
    if state["done"]:
        play.done = True
        play.finished_at = utcnow()
    session.add(play)
    session.flush()
    return play


# --- what players see ------------------------------------------------------------------------------


def _name(session: Session, group_id: int, user_id: int) -> str:
    member = session.exec(select(GroupMember).where(GroupMember.group_id == group_id, GroupMember.user_id == user_id)).first()
    player = session.get(Player, member.player_id) if member and member.player_id else None
    if player:
        return player.display_name
    user = session.get(User, user_id)
    return user.username if user else "Someone"


def leaderboard(session: Session, puzzle: DailyPuzzle) -> list[dict]:
    plays = session.exec(select(DailyPlay).where(DailyPlay.puzzle_id == puzzle.id, col(DailyPlay.done).is_(True))).all()
    plays = sorted(plays, key=lambda p: (-p.score, p.finished_at or utcnow()))
    return [{"user_id": p.user_id, "name": _name(session, puzzle.group_id, p.user_id), "score": p.score} for p in plays]


def streak(session: Session, group_id: int, user_id: int, day: str | None = None) -> int:
    """Days in a row this person finished the group's puzzle, up to today (or yesterday, if today's
    isn't done yet)."""
    day = day or today()
    finished = {
        pz.day
        for pz, _ in session.exec(
            select(DailyPuzzle, DailyPlay)
            .join(DailyPlay, col(DailyPlay.puzzle_id) == col(DailyPuzzle.id))
            .where(DailyPuzzle.group_id == group_id, DailyPlay.user_id == user_id, col(DailyPlay.done).is_(True))
        ).all()
    }
    if day not in finished:
        day = _previous(day)
    count = 0
    while day in finished:
        count += 1
        day = _previous(day)
    return count


def share_text(puzzle: DailyPuzzle, state: dict) -> str:
    """The spoiler-free result to post: one row per question."""
    lines = [f"Daily Statline #{puzzle.number} · {state['score']}/{state['max_score']}"]
    for q in state["questions"]:
        if q["id"] == "kda":
            row = " ".join(
                "".join("🟩" if p["hint"] == "exact" else "🟨" if p["close"] else "⬛" for p in g["parts"]) for g in q["guesses"]
            )
        elif q["id"] == "grade":
            row = "".join("🟩" if g["correct"] else "🟨" if g["close"] else "⬛" for g in q["guesses"])
        else:
            row = "".join("🟩" if g["correct"] else "🟥" for g in q["guesses"])
        lines.append(f"{q['label'].rstrip('?')}: {row}")
    return "\n".join(lines)


def view(session: Session, puzzle: DailyPuzzle, user: User) -> dict:
    """Everything the site and the bot show for one person: the clue, their guesses with feedback,
    and once they're done, the answer, the share text and the day's leaderboard."""
    ans = answer(session, puzzle)
    play = session.exec(select(DailyPlay).where(DailyPlay.puzzle_id == puzzle.id, DailyPlay.user_id == user.id)).first()
    state = progress(play, ans)
    out = {
        "number": puzzle.number,
        "day": puzzle.day,
        "clue": {k: ans[k] for k in ("champion_id", "role", "duration", "queue_id")},
        "players": [{"id": p.id, "name": p.display_name} for p in _group_players(session, puzzle.group_id)],
        "grades": rating.GRADES,
        **state,
        "streak": streak(session, puzzle.group_id, user.id, puzzle.day),
        "leaderboard": leaderboard(session, puzzle) if state["done"] else None,
        "answer": None,
        "share": None,
    }
    if state["done"]:
        out["answer"] = {
            "pilot": ans["pilot"],
            "pilot_name": session.get(Player, ans["pilot"]).display_name,
            "result": ans["result"],
            "kda": ans["kda"],
            "grade": ans["grade"],
            "game_id": ans["game_id"],
            "played_at": ans["played_at"],
        }
        out["share"] = share_text(puzzle, state)
    return out
