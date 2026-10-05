"""Game rules (SPEC section 7): spins, results, elimination, streaks, revive tokens and undo.

Every function works on a Session and leaves committing to the caller.
"""

import random
from collections.abc import Iterable
from dataclasses import dataclass

from sqlmodel import Session, col, select

from app.models import (
    ChallengeGame,
    Champion,
    Player,
    PoolEntry,
    PoolEvent,
    ReviveToken,
    Run,
    SpinAssignment,
    utcnow,
)
from app.services import spin as spin_logic

STREAK_TOKEN_INTERVAL = 3
RESULTS = ("win", "loss", "void")


class RuleError(Exception):
    """A rule was violated. `status` is the HTTP status the API should return."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


# --- helpers ---------------------------------------------------------------


def alive_champion_ids(session: Session, run_id: int) -> list[str]:
    rows = session.exec(
        select(PoolEntry.champion_id).where(PoolEntry.run_id == run_id, PoolEntry.status == "alive")
    )
    return sorted(rows.all())


def available_tokens(session: Session, run_id: int) -> list[ReviveToken]:
    return list(
        session.exec(
            select(ReviveToken).where(ReviveToken.run_id == run_id, col(ReviveToken.used_at).is_(None))
        ).all()
    )


def pending_game(session: Session, run_id: int) -> ChallengeGame | None:
    return session.exec(
        select(ChallengeGame).where(ChallengeGame.run_id == run_id, ChallengeGame.status == "pending")
    ).first()


def latest_game(session: Session, run_id: int) -> ChallengeGame | None:
    return session.exec(
        select(ChallengeGame).where(ChallengeGame.run_id == run_id).order_by(col(ChallengeGame.id).desc())
    ).first()


def assignments_for(session: Session, game_id: int) -> list[SpinAssignment]:
    return list(
        session.exec(
            select(SpinAssignment).where(SpinAssignment.game_id == game_id).order_by(col(SpinAssignment.id))
        ).all()
    )


def _require_active(run: Run) -> None:
    if run.status != "active":
        raise RuleError("This run has ended", 409)


def _require_pending(game: ChallengeGame) -> None:
    if game.status != "pending":
        raise RuleError(f"Game {game.id} is already resolved ({game.status})", 409)


def _validate_players(session: Session, player_ids: list[int]) -> None:
    if len(set(player_ids)) != len(player_ids):
        raise RuleError("A player can only be in a spin once")
    if not spin_logic.MIN_PLAYERS <= len(player_ids) <= spin_logic.MAX_PLAYERS:
        raise RuleError(
            f"A spin needs {spin_logic.MIN_PLAYERS} to {spin_logic.MAX_PLAYERS} players"
        )
    found = session.exec(select(Player.id).where(col(Player.id).in_(player_ids))).all()
    missing = set(player_ids) - set(found)
    if missing:
        raise RuleError(f"Unknown player id(s): {sorted(missing)}", 404)


# --- runs ------------------------------------------------------------------


def create_run(
    session: Session, name: str, options_per_player: int, champion_ids: Iterable[str] | None = None
) -> Run:
    if options_per_player not in spin_logic.ALLOWED_OPTIONS:
        raise RuleError("options_per_player must be 3 or 4")
    all_ids = set(session.exec(select(Champion.id)).all())
    if not all_ids:
        raise RuleError("No champions loaded yet. Refresh champions first.", 409)
    if champion_ids is None:
        chosen = all_ids
    else:
        chosen = set(champion_ids)
        unknown = chosen - all_ids
        if unknown:
            raise RuleError(f"Unknown champion id(s): {sorted(unknown)[:10]}")
        if not chosen:
            raise RuleError("A run needs at least one champion")

    run = Run(name=name, options_per_player=options_per_player)
    session.add(run)
    session.flush()
    for cid in sorted(chosen):
        session.add(PoolEntry(run_id=run.id, champion_id=cid))
    session.flush()
    return run


def end_run(session: Session, run: Run) -> Run:
    _require_active(run)
    game = pending_game(session, run.id)
    if game:
        game.status = "void"
        game.void_reason = "run ended"
        game.resolved_at = utcnow()
        session.add(game)
    run.status = "ended"
    run.ended_at = utcnow()
    session.add(run)
    session.flush()
    return run


@dataclass
class SpinStatus:
    alive_count: int
    options_per_player: int  # effective N for the given number of players; 0 = blocked
    blocked: bool
    tokens_available: int


def spin_status(session: Session, run: Run, n_players: int) -> SpinStatus:
    alive = len(alive_champion_ids(session, run.id))
    n = spin_logic.effective_options(alive, n_players, run.options_per_player)
    return SpinStatus(alive, n, n == 0, len(available_tokens(session, run.id)))


# --- spins -----------------------------------------------------------------


def draw_options(
    session: Session, run: Run, player_ids: list[int], rng: random.Random | None = None
) -> list[list[str]]:
    _require_active(run)
    _validate_players(session, player_ids)
    try:
        return spin_logic.draw(
            alive_champion_ids(session, run.id), len(player_ids), run.options_per_player, rng
        )
    except spin_logic.SpinBlocked as e:
        tokens = len(available_tokens(session, run.id))
        hint = f" {tokens} revive token(s) available." if tokens else " No revive tokens left."
        raise RuleError(str(e) + hint, 409) from e


def create_spin(
    session: Session, run: Run, player_ids: list[int], rng: random.Random | None = None
) -> ChallengeGame:
    """Spin for a challenge game. Only one game can be pending per run."""
    _require_active(run)
    existing = pending_game(session, run.id)
    if existing:
        raise RuleError(
            f"Game {existing.id} is still pending. Record its result or void it first.", 409
        )
    options = draw_options(session, run, player_ids, rng)
    game = ChallengeGame(run_id=run.id)
    session.add(game)
    session.flush()
    for pid, opts in zip(player_ids, options, strict=True):
        session.add(SpinAssignment(game_id=game.id, player_id=pid, options=opts))
    session.flush()
    return game


@dataclass
class Pick:
    player_id: int
    option_index: int | None = None  # 0-based index into the player's options
    champion_id: str | None = None  # used for "other" (not one of the options)


def set_played(session: Session, game: ChallengeGame, picks: list[Pick]) -> list[SpinAssignment]:
    _require_pending(game)
    by_player = {a.player_id: a for a in assignments_for(session, game.id)}
    for pick in picks:
        a = by_player.get(pick.player_id)
        if a is None:
            raise RuleError(f"Player {pick.player_id} is not in game {game.id}")
        if pick.option_index is not None:
            if not 0 <= pick.option_index < len(a.options):
                raise RuleError(f"Option {pick.option_index + 1} does not exist for this player")
            a.played_option_index = pick.option_index
            a.played_champion_id = a.options[pick.option_index]
        elif pick.champion_id is not None:
            if session.get(Champion, pick.champion_id) is None:
                raise RuleError(f"Unknown champion {pick.champion_id}")
            a.played_champion_id = pick.champion_id
            a.played_option_index = (
                a.options.index(pick.champion_id) if pick.champion_id in a.options else None
            )
        else:
            a.played_champion_id = None
            a.played_option_index = None
        session.add(a)

    played = [a.played_champion_id for a in by_player.values() if a.played_champion_id]
    if len(played) != len(set(played)):
        raise RuleError("Two players can't play the same champion")
    session.flush()
    return list(by_player.values())


# --- results ---------------------------------------------------------------


def apply_result(
    session: Session,
    game: ChallengeGame,
    result: str,
    source: str = "manual",
    void_reason: str | None = None,
) -> ChallengeGame:
    if result not in RESULTS:
        raise RuleError(f"Result must be one of {RESULTS}")
    _require_pending(game)
    run = session.get(Run, game.run_id)
    _require_active(run)
    assignments = assignments_for(session, game.id)

    if result == "loss":
        missing = [a.player_id for a in assignments if not a.played_champion_id]
        if missing:
            raise RuleError("Mark which champion every player played before recording a loss")

    game.prev_win_count = run.win_count
    game.prev_current_streak = run.current_streak
    game.prev_best_streak = run.best_streak
    now = utcnow()

    if result == "win":
        # Anyone left unmarked is assumed to have played their top option (players take the highest
        # one still available). Riot auto-results fill in the real champion instead.
        for a in assignments:
            if not a.played_champion_id and a.options:
                a.played_option_index = 0
                a.played_champion_id = a.options[0]
                session.add(a)
        run.win_count += 1
        run.current_streak += 1
        run.best_streak = max(run.best_streak, run.current_streak)
        if run.current_streak % STREAK_TOKEN_INTERVAL == 0:
            for a in assignments:
                session.add(ReviveToken(run_id=run.id, player_id=a.player_id, earned_in_game_id=game.id))
        game.status = "won"
    elif result == "loss":
        for a in assignments:
            entry = session.get(PoolEntry, (run.id, a.played_champion_id))
            if entry is None or entry.status != "alive":
                continue  # "other" pick outside the pool, or already gone
            entry.status = "eliminated"
            entry.eliminated_at = now
            entry.eliminated_in_game_id = game.id
            entry.eliminated_by_player_id = a.player_id
            session.add(entry)
            session.add(
                PoolEvent(
                    run_id=run.id,
                    game_id=game.id,
                    type="eliminate",
                    champion_id=a.played_champion_id,
                    player_id=a.player_id,
                )
            )
        run.current_streak = 0
        game.status = "lost"
    else:
        game.status = "void"
        game.void_reason = void_reason or "manual void"

    game.result_source = source
    game.resolved_at = now
    session.add(run)
    session.add(game)
    session.flush()
    return game


def void_spin(session: Session, game: ChallengeGame, reason: str = "re-roll") -> ChallengeGame:
    """Explicit re-roll: void the pending game so a new spin can be made. Logged via void_reason."""
    return apply_result(session, game, "void", void_reason=reason)


def undo_result(session: Session, game: ChallengeGame) -> ChallengeGame:
    """Reverse the result of the most recent game in its run and put it back to pending."""
    if game.status == "pending":
        raise RuleError("This game has no result to undo", 409)
    latest = latest_game(session, game.run_id)
    if latest is None or latest.id != game.id:
        raise RuleError("Only the most recent game can be undone", 409)
    run = session.get(Run, game.run_id)
    _require_active(run)

    earned = session.exec(select(ReviveToken).where(ReviveToken.earned_in_game_id == game.id)).all()
    if any(t.used_at for t in earned):
        raise RuleError("A revive token earned in this game was already used", 409)
    for t in earned:
        session.delete(t)

    events = session.exec(
        select(PoolEvent).where(PoolEvent.game_id == game.id, col(PoolEvent.undone).is_(False))
    ).all()
    for ev in events:
        if ev.type == "eliminate":
            entry = session.get(PoolEntry, (run.id, ev.champion_id))
            if entry and entry.status == "eliminated" and entry.eliminated_in_game_id == game.id:
                _make_alive(entry)
                session.add(entry)
        ev.undone = True
        session.add(ev)

    if game.prev_win_count is not None:
        run.win_count = game.prev_win_count
        run.current_streak = game.prev_current_streak
        run.best_streak = game.prev_best_streak
    session.add(run)

    game.status = "pending"
    game.result_source = None
    game.resolved_at = None
    game.void_reason = None
    game.prev_win_count = game.prev_current_streak = game.prev_best_streak = None
    session.add(game)
    session.flush()
    return game


# --- pool edits and tokens ---------------------------------------------------


def _make_alive(entry: PoolEntry) -> None:
    entry.status = "alive"
    entry.eliminated_at = None
    entry.eliminated_in_game_id = None
    entry.eliminated_by_player_id = None


def _get_entry(session: Session, run_id: int, champion_id: str) -> PoolEntry:
    entry = session.get(PoolEntry, (run_id, champion_id))
    if entry is None:
        raise RuleError(f"{champion_id} is not in this run's pool", 404)
    return entry


def use_token(session: Session, token: ReviveToken, champion_id: str) -> ReviveToken:
    if token.used_at is not None:
        raise RuleError("This token was already used", 409)
    run = session.get(Run, token.run_id)
    _require_active(run)
    entry = _get_entry(session, run.id, champion_id)
    if entry.status != "eliminated":
        raise RuleError(f"{champion_id} is not eliminated", 409)
    _make_alive(entry)
    token.used_at = utcnow()
    token.revived_champion_id = champion_id
    session.add_all([entry, token])
    session.add(
        PoolEvent(
            run_id=run.id, type="revive", champion_id=champion_id, player_id=token.player_id, token_id=token.id
        )
    )
    session.flush()
    return token


def manual_eliminate(session: Session, run: Run, champion_id: str) -> PoolEntry:
    _require_active(run)
    entry = _get_entry(session, run.id, champion_id)
    if entry.status != "alive":
        raise RuleError(f"{champion_id} is already eliminated", 409)
    entry.status = "eliminated"
    entry.eliminated_at = utcnow()
    session.add(entry)
    session.add(PoolEvent(run_id=run.id, type="manual_eliminate", champion_id=champion_id))
    session.flush()
    return entry


def manual_revive(session: Session, run: Run, champion_id: str) -> PoolEntry:
    _require_active(run)
    entry = _get_entry(session, run.id, champion_id)
    if entry.status != "eliminated":
        raise RuleError(f"{champion_id} is not eliminated", 409)
    _make_alive(entry)
    session.add(entry)
    session.add(PoolEvent(run_id=run.id, type="manual_revive", champion_id=champion_id))
    session.flush()
    return entry
