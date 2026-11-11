"""Daily Statline (SPEC 20): picking statlines, guessing, scoring, streaks, the API and the bot."""

import asyncio
import random
from datetime import UTC, datetime, timedelta

import pytest
from sqlmodel import Session, select

from app.models import (
    AppSettings,
    ChallengeGame,
    DailyPlay,
    DailyPuzzle,
    DiscordLink,
    GroupMember,
    PlayerMatchStats,
    RiotMatch,
    Run,
)
from app.services import daily, discord_bot, rules
from tests.conftest import GROUP, make_user
from tests.factories import FakeDiscord

# Alex 7/2/11 S- on Champ003 (key 1003), Bea 1/8/3 C on Champ004, in one won game; Cal in a lost game.
LINES = {
    "G1": [(1, 1003, 7, 2, 11, "S-", True), (2, 1004, 1, 8, 3, "C", True)],
    "G2": [(3, 1005, 4, 4, 4, None, False)],
}


@pytest.fixture
def history(session):
    run = rules.create_run(session, "Run", 3, group_id=GROUP)
    games = {}
    for mid, lines in LINES.items():
        game = ChallengeGame(run_id=run.id, status="won" if lines[0][6] else "lost", riot_match_id=mid)
        session.add(game)
        session.add(RiotMatch(match_id=mid, queue_id=400, game_duration=1880))
        session.flush()
        games[mid] = game
        for pid, key, k, d, a, grade, win in lines:
            session.add(
                PlayerMatchStats(
                    match_id=mid, player_id=pid, champion_key=key, team_id=100, team_position="MIDDLE", win=win,
                    kills=k, deaths=d, assists=a, rating_grade=grade, is_challenge=True, challenge_game_id=game.id,
                )
            )
    # A pending game and a non-challenge game never count.
    session.add(ChallengeGame(run_id=run.id))
    session.add(RiotMatch(match_id="G3", queue_id=400))
    session.flush()
    session.add(PlayerMatchStats(match_id="G3", player_id=4, champion_key=1006, team_id=100, win=True))
    session.commit()
    return games


def pick(session, match_id, player_id, day=None) -> DailyPuzzle:
    """Today's puzzle, made from a chosen statline."""
    day = day or daily.today()
    game = session.exec(select(ChallengeGame).where(ChallengeGame.riot_match_id == match_id)).first()
    number = len(session.exec(select(DailyPuzzle)).all()) + 1
    p = DailyPuzzle(group_id=GROUP, day=day, number=number, match_id=match_id, player_id=player_id, game_id=game.id)
    session.add(p)
    session.commit()
    return p


def test_candidates_are_finished_challenge_lines_never_used_twice(session, history):
    lines = {(p.match_id, p.player_id) for p in daily.candidates(session, GROUP)}
    assert lines == {("G1", 1), ("G1", 2), ("G2", 3)}
    first = daily.puzzle_for(session, GROUP, "2026-11-01", rng=random.Random(1))
    session.commit()
    assert daily.puzzle_for(session, GROUP, "2026-11-01") .id == first.id  # same puzzle all day
    second = daily.puzzle_for(session, GROUP, "2026-11-02", rng=random.Random(1))
    third = daily.puzzle_for(session, GROUP, "2026-11-03", rng=random.Random(1))
    used = {(p.match_id, p.player_id) for p in (first, second, third)}
    assert used == lines  # every line once, including two from the same game
    assert [p.number for p in (first, second, third)] == [1, 2, 3]
    assert daily.puzzle_for(session, GROUP, "2026-11-04") is None  # nothing left


def test_no_history_no_puzzle(session):
    assert daily.puzzle_for(session, GROUP) is None


def test_days_turn_over_at_midnight_in_the_daily_time_zone():
    # 03:30 UTC on Nov 12 is still Nov 11 in New York.
    assert daily.today(datetime(2026, 11, 12, 3, 30, tzinfo=UTC)) == "2026-11-11"
    assert daily.today(datetime(2026, 11, 12, 5, 30, tzinfo=UTC)) == "2026-11-12"


def test_a_perfect_game_scores_ten(session, history, owner):
    puzzle = pick(session, "G1", 1)
    for q, v in (("result", "win"), ("pilot", 1), ("kda", [7, 2, 11]), ("grade", "S-")):
        daily.guess(session, puzzle, owner, q, v)
    v = daily.view(session, puzzle, owner)
    assert v["done"] and v["score"] == 10 == v["max_score"]
    assert v["answer"]["pilot_name"] == "Alex" and v["answer"]["kda"] == [7, 2, 11]
    assert v["share"].splitlines()[0] == f"Daily Statline #{puzzle.number} · 10/10"
    assert v["leaderboard"] == [{"user_id": owner.id, "name": "owner", "score": 10}]
    with pytest.raises(rules.RuleError):
        daily.guess(session, puzzle, owner, "result", "win")


def test_hints_tries_and_points(session, history, owner):
    puzzle = pick(session, "G1", 1)
    with pytest.raises(rules.RuleError, match="first"):
        daily.guess(session, puzzle, owner, "pilot", 1)  # questions go in order
    daily.guess(session, puzzle, owner, "result", "loss")  # wrong, and that's its only try
    daily.guess(session, puzzle, owner, "pilot", 2)
    with pytest.raises(rules.RuleError, match="already"):
        daily.guess(session, puzzle, owner, "pilot", 2)
    daily.guess(session, puzzle, owner, "pilot", 1)  # right on the second try: 1 point
    daily.guess(session, puzzle, owner, "kda", [9, 2, 3])
    v = daily.view(session, puzzle, owner)
    kda = next(q for q in v["questions"] if q["id"] == "kda")
    hints = [(p["hint"], p["close"]) for p in kda["guesses"][0]["parts"]]
    assert hints == [("lower", True), ("exact", False), ("higher", False)]
    for guess in ([7, 2, 10], [7, 2, 12], [7, 2, 20]):
        daily.guess(session, puzzle, owner, "kda", guess)  # no limit on guesses, -1 point each
    kda = next(q for q in daily.view(session, puzzle, owner)["questions"] if q["id"] == "kda")
    assert (kda["tries"], kda["worth"], kda["finished"]) == (None, 0, False)
    daily.guess(session, puzzle, owner, "kda", [7, 2, 11])  # right after 4 misses: 0 points
    daily.guess(session, puzzle, owner, "grade", "A+")
    grade = next(q for q in daily.view(session, puzzle, owner)["questions"] if q["id"] == "grade")
    assert (grade["guesses"][0]["hint"], grade["guesses"][0]["close"]) == ("higher", True)  # S- is one better
    assert grade["worth"] == 2
    daily.guess(session, puzzle, owner, "grade", "S-")  # one miss: 2 points
    v = daily.view(session, puzzle, owner)
    assert v["done"] and v["score"] == 0 + 1 + 0 + 2
    assert v["share"].splitlines()[1:] == [
        "Win or loss: 🟥",
        "Who was piloting: 🟥🟩",
        "K / D / A: 🟨🟩⬛ 🟩🟩🟨 🟩🟩🟨 🟩🟩⬛ 🟩🟩🟩",
        "Grade: 🟨🟩",
    ]


def test_kda_misses_cost_a_point_each(session, history, owner):
    puzzle = pick(session, "G1", 1)
    daily.guess(session, puzzle, owner, "result", "win")
    daily.guess(session, puzzle, owner, "pilot", 1)
    daily.guess(session, puzzle, owner, "kda", [7, 2, 12])
    daily.guess(session, puzzle, owner, "kda", [7, 2, 11])  # one miss: 3 of 4
    kda = next(q for q in daily.view(session, puzzle, owner)["questions"] if q["id"] == "kda")
    assert (kda["solved"], kda["points"]) == (True, 3)


def test_bad_guesses_are_refused(session, history, owner):
    puzzle = pick(session, "G1", 1)
    for q, v in (("result", "maybe"), ("result", None)):
        with pytest.raises(rules.RuleError):
            daily.guess(session, puzzle, owner, q, v)
    daily.guess(session, puzzle, owner, "result", "win")
    with pytest.raises(rules.RuleError, match="group"):
        daily.guess(session, puzzle, owner, "pilot", 9999)
    daily.guess(session, puzzle, owner, "pilot", 1)
    for v in ([1, 2], [1, 2, 300], ["a", 1, 2]):
        with pytest.raises(rules.RuleError):
            daily.guess(session, puzzle, owner, "kda", v)


def test_no_grade_means_three_questions(session, history, owner):
    puzzle = pick(session, "G2", 3)
    for q, v in (("result", "loss"), ("pilot", 3), ("kda", [4, 4, 4])):
        daily.guess(session, puzzle, owner, q, v)
    v = daily.view(session, puzzle, owner)
    assert v["done"] and v["score"] == v["max_score"] == 7 and [q["id"] for q in v["questions"]] == ["result", "pilot", "kda"]


def test_old_puzzles_cant_be_played(session, history, owner):
    old = pick(session, "G1", 1, day="2026-01-01")
    with pytest.raises(rules.RuleError, match="over"):
        daily.guess(session, old, owner, "result", "win")


def test_streaks_count_days_in_a_row(session, history, owner):
    for day, mid, pid in (("2026-11-01", "G1", 1), ("2026-11-02", "G1", 2), ("2026-11-04", "G2", 3)):
        p = pick(session, mid, pid, day=day)
        session.add(DailyPlay(puzzle_id=p.id, user_id=owner.id, done=True, score=5, finished_at=datetime.now(UTC)))
    session.commit()
    assert daily.streak(session, GROUP, owner.id, "2026-11-04") == 1
    assert daily.streak(session, GROUP, owner.id, "2026-11-02") == 2
    assert daily.streak(session, GROUP, owner.id, "2026-11-03") == 2  # today not done yet: counts to yesterday
    assert daily.streak(session, GROUP, owner.id, "2026-11-06") == 0


# --- the site --------------------------------------------------------------------------------------


def test_api(client, session, history, sign_in):
    out = client.get("/api/daily").json()
    assert out["available"] and out["number"] == 1 and out["current"] == "result" and out["answer"] is None
    assert out["clue"]["duration"] == 1880 and out["clue"]["queue_id"] == 400
    assert client.post("/api/daily/guess", json={"question": "pilot", "value": 1}).status_code == 409
    out = client.post("/api/daily/guess", json={"question": "result", "value": "win"}).json()
    assert out["current"] == "pilot"
    # Bea plays the same puzzle separately.
    bea = sign_in(make_user(session, "bea", player_id=2))
    assert bea.get("/api/daily").json()["number"] == 1 and bea.get("/api/daily").json()["current"] == "result"
    assert client.post("/api/daily/guess", json={"question": "kda", "value": "nope"}).status_code in (409, 422)


def test_api_without_history(client):
    assert client.get("/api/daily").json() == {"available": False}


# --- the bot ---------------------------------------------------------------------------------------


@pytest.fixture
def linked(session, owner, history):
    m = session.exec(select(GroupMember).where(GroupMember.user_id == owner.id)).one()
    m.player_id = 4
    owner.discord_id = "d-owner"
    session.add_all([m, owner, DiscordLink(group_id=GROUP, guild_id="g1", channel_id="c1")])
    session.commit()
    return owner


def interaction(type_, data, user="d-owner"):
    return {"type": type_, "token": "t", "guild_id": "g1", "member": {"user": {"id": user}}, "data": data, "message": {"id": "m", "channel_id": "c1"}}


def test_play_through_discord(session, linked):
    puzzle = pick(session, "G1", 1)
    a = discord_bot.handle(session, interaction(2, {"name": "daily"}))
    assert a.response["type"] == discord_bot.MESSAGE and a.response["data"]["flags"] == 64
    embed = a.response["data"]["embeds"][0]
    assert embed["title"] == f"Daily Statline #{puzzle.number}" and "Champ 3" in embed["description"]
    a = discord_bot.handle(session, interaction(3, {"custom_id": "hd:dq:result:win"}))
    assert a.response["type"] == discord_bot.UPDATE and "Win ✅" in a.response["data"]["embeds"][0]["description"]
    menu = a.response["data"]["components"][0]["components"][0]
    assert menu["custom_id"] == "hd:dq:pilot" and {o["label"] for o in menu["options"]} >= {"Alex", "Bea"}
    a = discord_bot.handle(session, interaction(3, {"custom_id": "hd:dq:pilot", "values": ["1"]}))
    assert "Alex ✅" in a.response["data"]["embeds"][0]["description"]
    modal = discord_bot.handle(session, interaction(3, {"custom_id": "hd:dq:kda"}))
    assert modal.response["type"] == discord_bot.MODAL and modal.response["data"]["custom_id"] == "hd:dqm:kda"
    fields = lambda k, d, a_: [{"type": 1, "components": [{"type": 4, "custom_id": c, "value": v}]} for c, v in (("k", k), ("d", d), ("a", a_))]  # noqa: E731
    a = discord_bot.handle(session, interaction(5, {"custom_id": "hd:dqm:kda", "components": fields("x", "2", "11")}))
    assert "whole numbers" in a.response["data"]["content"]
    a = discord_bot.handle(session, interaction(5, {"custom_id": "hd:dqm:kda", "components": fields("7", "2", "11")}))
    assert "7✅ / 2✅ / 11✅" in a.response["data"]["embeds"][0]["description"]
    a = discord_bot.handle(session, interaction(3, {"custom_id": "hd:dq:grade", "values": ["S-"]}))
    desc = a.response["data"]["embeds"][0]["description"]
    assert "It was **Alex**" in desc and "Score **10/10**" in desc
    share = discord_bot.handle(session, interaction(3, {"custom_id": "hd:dq:share"}))
    assert "flags" not in share.response["data"] and "Daily Statline #" in share.response["data"]["content"]
    assert "Alex" not in share.response["data"]["content"].split("\n", 1)[1]  # no spoilers past the name line
    # The same guesses show on the site.
    session.expire_all()
    assert session.exec(select(DailyPlay)).one().score == 10


def test_unlinked_people_cant_play(session, linked):
    pick(session, "G1", 1)
    assert "Link your Discord" in discord_bot.handle(session, interaction(2, {"name": "daily"}, user="d-x")).response["data"]["content"]


def test_daily_post_once_a_day_with_yesterdays_answer(session, linked, engine, owner):
    yesterday = pick(session, "G1", 1, day=(datetime.fromisoformat(daily.today()) - timedelta(days=1)).date().isoformat())
    session.add(DailyPlay(puzzle_id=yesterday.id, user_id=owner.id, done=True, score=8, finished_at=datetime.now(UTC)))
    session.commit()
    fake = FakeDiscord()
    new = lambda: Session(engine)  # noqa: E731
    assert asyncio.run(discord_bot.post_daily(new, fake)) == 1
    assert asyncio.run(discord_bot.post_daily(new, fake)) == 0
    msg = fake.posts[0][1]
    text = msg["embeds"][0]["description"]
    assert msg["embeds"][0]["title"] == "Daily Statline #2"
    assert "Yesterday (#1): **Alex** on Champ 3 · Win · 7/2/11 · S-" in text
    assert "Scores: Dee 8/10" in text  # the owner plays as Dee here
    assert msg["components"][0]["components"][0]["custom_id"] == "hd:dq:open"
    session.expire_all()
    link = session.exec(select(DiscordLink)).one()
    assert link.state["daily"] == daily.today()
    # Switched off: nothing.
    link.muted = ["daily"]
    link.state = {}
    session.add(link)
    session.commit()
    assert asyncio.run(discord_bot.post_daily(new, fake)) == 0
