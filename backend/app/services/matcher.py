"""Links Riot matches to challenge games (SPEC 9.3).

Works only from matches already imported into RiotMatch / PlayerMatchStats, so it makes no API
calls itself: the poller (or "Sync now") imports recent matches first, then calls `match_pending`.

For a pending game the matcher finds the earliest match, starting after the spin, that every
player in the game played. Then it checks, in order:
  1. the queue is allowed,
  2. all players were on the same team,
  3. it wasn't a remake (if it was, the game is voided),
  4. each player's champion was one of their spin options.
All checks pass -> the result is applied (result_source "auto"). A check fails -> the game is
flagged needs_review and nothing changes until the user accepts or rejects the match.
"""

from dataclasses import dataclass
from datetime import timedelta

from sqlmodel import Session, col, select

from app.models import (
    AppSettings,
    ChallengeGame,
    Champion,
    Player,
    PlayerMatchStats,
    RiotMatch,
    Run,
    SpinAssignment,
)
from app.services import rules

# Matches that started a little before the spin still count (clock drift, spinning in champ select).
START_BUFFER = timedelta(minutes=5)


@dataclass
class Outcome:
    game_id: int
    status: str  # "applied" | "voided" | "needs_review" | "waiting" | "unlinked" | "linked" | "skipped"
    message: str = ""
    match_id: str | None = None


@dataclass
class Candidate:
    match: RiotMatch
    rows: dict[int, PlayerMatchStats]  # player_id -> stats row


def find_candidate(session: Session, game: ChallengeGame) -> Candidate | None:
    assignments = rules.assignments_for(session, game.id)
    player_ids = [a.player_id for a in assignments]
    taken = set(
        session.exec(
            select(ChallengeGame.riot_match_id).where(
                col(ChallengeGame.riot_match_id).is_not(None), ChallengeGame.id != game.id
            )
        ).all()
    )
    rows = session.exec(
        select(PlayerMatchStats, RiotMatch)
        .join(RiotMatch, col(RiotMatch.match_id) == col(PlayerMatchStats.match_id))
        .where(
            col(PlayerMatchStats.player_id).in_(player_ids),
            col(RiotMatch.game_start) >= game.created_at - START_BUFFER,
        )
    ).all()
    by_match: dict[str, Candidate] = {}
    for pms, match in rows:
        if match.match_id in taken or match.match_id in game.rejected_match_ids:
            continue
        by_match.setdefault(match.match_id, Candidate(match, {})).rows[pms.player_id] = pms
    complete = [c for c in by_match.values() if len(c.rows) == len(player_ids)]
    return min(complete, key=lambda c: c.match.game_start) if complete else None


@dataclass
class CheckResult:
    ok: bool
    remake: bool = False
    win: bool = False
    problems: list[str] | None = None
    played: dict[int, str | None] | None = None  # player_id -> champion id


def check(session: Session, game: ChallengeGame, cand: Candidate, settings: AppSettings) -> CheckResult:
    champ_by_key = {c.key: c.id for c in session.exec(select(Champion)).all()}
    assignments = {a.player_id: a for a in rules.assignments_for(session, game.id)}
    names = {p.id: p.display_name for p in session.exec(select(Player)).all()}
    played = {pid: champ_by_key.get(row.champion_key) for pid, row in cand.rows.items()}
    problems: list[str] = []

    if cand.match.queue_id not in settings.allowed_queue_ids:
        problems.append(f"Queue {cand.match.queue_id} isn't one of the allowed challenge queues")
    if len({row.team_id for row in cand.rows.values()}) > 1:
        problems.append("Players were on different teams")
    remake = cand.match.early_surrender or cand.match.game_duration < settings.remake_threshold_seconds
    if not problems and not remake:
        for pid, cid in played.items():
            if cid not in assignments[pid].options:
                champ = cid or f"champion #{cand.rows[pid].champion_key}"
                problems.append(f"{names.get(pid, pid)} played {champ}, which wasn't one of their options")
    win = all(row.win for row in cand.rows.values())
    return CheckResult(not problems, remake, win, problems, played)


def link_stats(session: Session, game: ChallengeGame, cand: Candidate) -> None:
    game.riot_match_id = cand.match.match_id
    for row in cand.rows.values():
        row.is_challenge = True
        row.challenge_game_id = game.id
        session.add(row)
    session.add(game)


def _picks(result: CheckResult) -> list[rules.Pick]:
    return [rules.Pick(player_id=pid, champion_id=cid) for pid, cid in (result.played or {}).items() if cid]


def match_pending(session: Session, game: ChallengeGame, settings: AppSettings) -> Outcome:
    """Try to resolve one pending game from imported matches. Never raises for normal cases."""
    if game.status != "pending":
        return Outcome(game.id, "skipped", "Game is not pending")
    if not settings.challenge_mode:
        return Outcome(game.id, "skipped", "Challenge mode is off")
    if game.needs_review:
        return Outcome(game.id, "needs_review", game.review_reason or "", game.riot_match_id)
    run = session.get(Run, game.run_id)
    if run is None or run.status != "active":
        return Outcome(game.id, "skipped", "Run is not active")

    player_ids = [a.player_id for a in rules.assignments_for(session, game.id)]
    unlinked = session.exec(
        select(Player.display_name).where(col(Player.id).in_(player_ids), col(Player.puuid).is_(None))
    ).all()
    if unlinked:
        return Outcome(game.id, "unlinked", f"Not linked to Riot: {', '.join(unlinked)}")

    cand = find_candidate(session, game)
    if cand is None:
        return Outcome(game.id, "waiting", "No match found yet")

    result = check(session, game, cand, settings)
    if not result.ok:
        game.needs_review = True
        game.review_reason = "; ".join(result.problems or [])
        game.riot_match_id = cand.match.match_id
        session.add(game)
        session.flush()
        return Outcome(game.id, "needs_review", game.review_reason, cand.match.match_id)

    if result.remake:
        rules.apply_result(session, game, "void", source="auto", void_reason="remake")
        link_stats(session, game, cand)
        session.flush()
        return Outcome(game.id, "voided", "Remake", cand.match.match_id)

    rules.set_played(session, game, _picks(result))
    rules.apply_result(session, game, "win" if result.win else "loss", source="auto")
    link_stats(session, game, cand)
    session.flush()
    return Outcome(game.id, "applied", "Win" if result.win else "Loss", cand.match.match_id)


def accept_review(session: Session, game: ChallengeGame, settings: AppSettings) -> ChallengeGame:
    """Apply the flagged match anyway, using Riot's champions (as "other" picks if needed) and result."""
    if not game.needs_review or not game.riot_match_id:
        raise rules.RuleError("This game has no match waiting for review", 409)
    player_ids = [a.player_id for a in rules.assignments_for(session, game.id)]
    rows = {
        r.player_id: r
        for r in session.exec(
            select(PlayerMatchStats).where(
                PlayerMatchStats.match_id == game.riot_match_id, col(PlayerMatchStats.player_id).in_(player_ids)
            )
        ).all()
    }
    cand = Candidate(session.get(RiotMatch, game.riot_match_id), rows)
    result = check(session, game, cand, settings)
    game.needs_review = False
    game.review_reason = None
    game.riot_match_id = None  # set again by link_stats below
    if result.remake:
        rules.apply_result(session, game, "void", source="auto", void_reason="remake")
    else:
        missing = [pid for pid in player_ids if not (result.played or {}).get(pid)]
        if missing:
            raise rules.RuleError("This match is missing a player's champion. Record the result by hand.", 409)
        rules.set_played(session, game, _picks(result))
        rules.apply_result(session, game, "win" if result.win else "loss", source="auto")
    link_stats(session, game, cand)
    session.flush()
    return game


def reject_review(session: Session, game: ChallengeGame) -> ChallengeGame:
    """Ignore the flagged match; the matcher will look for a different one."""
    if not game.needs_review or not game.riot_match_id:
        raise rules.RuleError("This game has no match waiting for review", 409)
    game.rejected_match_ids = [*game.rejected_match_ids, game.riot_match_id]
    game.riot_match_id = None
    game.needs_review = False
    game.review_reason = None
    session.add(game)
    session.flush()
    return game


def link_manual_game(session: Session, game: ChallengeGame, settings: AppSettings) -> Outcome:
    """Attach Riot stats to a game whose result was recorded by hand. Never changes the result or the pool.

    Links only when the match passes every check, Riot agrees with the recorded result, and (for a
    loss) the marked champions match what was played. A win's champions are corrected from Riot,
    since a manual win may have assumed option 1.
    """
    if game.status not in ("won", "lost") or game.riot_match_id:
        return Outcome(game.id, "skipped")
    cand = find_candidate(session, game)
    if cand is None:
        return Outcome(game.id, "waiting")
    result = check(session, game, cand, settings)
    if not result.ok or result.remake or result.win != (game.status == "won"):
        return Outcome(game.id, "skipped", "Match doesn't agree with the recorded result")
    assignments = {a.player_id: a for a in rules.assignments_for(session, game.id)}
    played = result.played or {}
    if game.status == "lost" and any(assignments[pid].played_champion_id != cid for pid, cid in played.items()):
        return Outcome(game.id, "skipped", "Marked champions differ from the match")
    for pid, cid in played.items():
        a = assignments[pid]
        a.played_champion_id = cid
        a.played_option_index = a.options.index(cid)
        session.add(a)
    link_stats(session, game, cand)
    session.flush()
    return Outcome(game.id, "linked", "", cand.match.match_id)


def run_matcher(session: Session, recent_manual_days: int = 7) -> list[Outcome]:
    """Match every pending game in active runs, then link recent hand-recorded games for stats."""
    settings = session.get(AppSettings, 1) or AppSettings()
    outcomes: list[Outcome] = []
    active_runs = select(Run.id).where(Run.status == "active")
    pending = session.exec(
        select(ChallengeGame).where(ChallengeGame.status == "pending", col(ChallengeGame.run_id).in_(active_runs))
    ).all()
    for game in pending:
        outcomes.append(match_pending(session, game, settings))

    since = rules.utcnow() - timedelta(days=recent_manual_days)
    manual = session.exec(
        select(ChallengeGame).where(
            col(ChallengeGame.status).in_(["won", "lost"]),
            col(ChallengeGame.riot_match_id).is_(None),
            col(ChallengeGame.created_at) >= since,
        )
    ).all()
    for game in manual:
        if session.exec(select(Player.id).join(SpinAssignment, col(SpinAssignment.player_id) == col(Player.id)).where(
            SpinAssignment.game_id == game.id, col(Player.puuid).is_(None)
        )).first():
            continue
        outcome = link_manual_game(session, game, settings)
        if outcome.status == "linked":
            outcomes.append(outcome)
    return outcomes
