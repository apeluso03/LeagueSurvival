"""Clearing test data out of a group (app/cleanup_cli.py): voided games and games from before the
current run started, and every run other than the current one.

Deleting a game takes everything that points at it with it: spins, the live game, pool events,
gold, revive tokens earned in it, Daily Statline puzzles on it and the bot's messages about it. A
finished game's eliminations are undone (those champions come back), and the run's wins and
streaks are counted again from the games left. Riot matches stay as plain stats (no longer linked
to a challenge game).
"""

from dataclasses import dataclass, field

from sqlmodel import Session, col, delete, select

from app.models import (
    AppSettings,
    ChallengeGame,
    Contract,
    DailyPlay,
    DailyPuzzle,
    DiscordMessage,
    GoldLedger,
    InventoryItem,
    LiveGame,
    PlayerMatchStats,
    PoolEntry,
    PoolEvent,
    ReviveToken,
    Run,
    SpinAssignment,
)
from app.services import rules

GAME_MESSAGES = ("spin", "live", "result", "nudge")  # DiscordMessage kinds keyed by game id


@dataclass
class Plan:
    group_id: int
    run: Run | None  # the current run (kept)
    other_runs: list[tuple[Run, int]] = field(default_factory=list)  # (run, games in it): deleted whole
    voided: list[ChallengeGame] = field(default_factory=list)  # in the current run
    before_start: list[ChallengeGame] = field(default_factory=list)  # in the current run, not voided
    blocked: dict[int, str] = field(default_factory=dict)  # game id -> why it can't be removed

    @property
    def games(self) -> list[ChallengeGame]:
        return [g for g in self.voided + self.before_start if g.id not in self.blocked]

    @property
    def empty(self) -> bool:
        return not (self.other_runs or self.games)


def plan(session: Session, group_id: int) -> Plan:
    settings = session.exec(select(AppSettings).where(AppSettings.group_id == group_id)).first()
    run = session.get(Run, settings.active_run_id) if settings and settings.active_run_id else None
    out = Plan(group_id=group_id, run=run)
    for r in session.exec(select(Run).where(Run.group_id == group_id).order_by(col(Run.id))).all():
        if run is None or r.id != run.id:
            n = len(session.exec(select(ChallengeGame.id).where(ChallengeGame.run_id == r.id)).all())
            out.other_runs.append((r, n))
    if run is None:
        return out
    for g in session.exec(select(ChallengeGame).where(ChallengeGame.run_id == run.id).order_by(col(ChallengeGame.id))).all():
        if g.status == "void":
            out.voided.append(g)
        elif g.created_at < run.started_at:
            out.before_start.append(g)
            if g.status == "pending":
                continue
            used = session.exec(
                select(ReviveToken).where(ReviveToken.earned_in_game_id == g.id, col(ReviveToken.used_at).is_not(None))
            ).first()
            if used:
                out.blocked[g.id] = "a revive token earned in it was already spent"
    return out


def describe(session: Session, p: Plan) -> str:
    lines = []
    if p.run is None:
        lines.append(f"Group {p.group_id} has no current run; every run below would be deleted.")
    else:
        lines.append(f"Current run (kept): #{p.run.id} {p.run.name!r}, started {p.run.started_at:%Y-%m-%d %H:%M} UTC")
    for r, n in p.other_runs:
        lines.append(f"  delete run #{r.id} {r.name!r} ({r.status}, {n} games)")
    numbers = rules.game_numbers(session, [p.run.id]) if p.run else {}
    for g in p.voided:
        lines.append(f"  delete voided game id {g.id} ({g.created_at:%Y-%m-%d %H:%M}, {g.void_reason or 'void'})")
    for g in p.before_start:
        why = p.blocked.get(g.id)
        verb = f"KEEP (can't remove: {why})" if why else "delete"
        lines.append(f"  {verb} game id {g.id} from before the run started ({g.status}, {g.created_at:%Y-%m-%d %H:%M}, shown as game {numbers.get(g.id)})")
    if p.empty:
        lines.append("  nothing to remove")
    return "\n".join(lines)


def delete_game(session: Session, game: ChallengeGame) -> None:
    """Remove one game and everything that points at it (see the module docstring)."""
    gid = game.id
    run = session.get(Run, game.run_id)
    if game.status in ("won", "lost"):
        from app.services import economy  # local: economy imports rules

        economy.reverse_game(session, game)  # contracts settled by it go back to waiting
        for entry in session.exec(
            select(PoolEntry).where(PoolEntry.run_id == run.id, PoolEntry.eliminated_in_game_id == gid)
        ).all():
            if entry.status == "eliminated":
                rules._make_alive(entry)
                session.add(entry)
        for ev in session.exec(select(PoolEvent).where(PoolEvent.game_id == gid, PoolEvent.type == "shield_consumed")).all():
            entry = session.get(PoolEntry, (run.id, ev.champion_id))
            shield = session.get(InventoryItem, ev.item_id) if ev.item_id else None
            if entry and shield and not ev.undone and entry.shield_item_id is None:
                entry.shield_item_id = shield.id  # the shield it used up goes back on
                shield.status, shield.used_at, shield.used_in_game_id = "active", None, None
                session.add_all([entry, shield])
    for entry in session.exec(select(PoolEntry).where(PoolEntry.eliminated_in_game_id == gid)).all():
        entry.eliminated_in_game_id = None
        session.add(entry)
    for item in session.exec(select(InventoryItem).where(InventoryItem.used_in_game_id == gid)).all():
        item.used_in_game_id = None
        session.add(item)
    for c in session.exec(select(Contract).where(Contract.game_id == gid)).all():
        c.game_id = None
        session.add(c)
    for pms in session.exec(select(PlayerMatchStats).where(PlayerMatchStats.challenge_game_id == gid)).all():
        pms.is_challenge = False
        pms.challenge_game_id = None
        session.add(pms)
    puzzles = session.exec(select(DailyPuzzle.id).where(DailyPuzzle.game_id == gid)).all()
    if puzzles:
        session.exec(delete(DailyPlay).where(col(DailyPlay.puzzle_id).in_(puzzles)))
        session.exec(delete(DailyPuzzle).where(col(DailyPuzzle.id).in_(puzzles)))
    session.exec(delete(DiscordMessage).where(col(DiscordMessage.ref_id) == gid, col(DiscordMessage.kind).in_(GAME_MESSAGES)))
    session.exec(delete(ReviveToken).where(ReviveToken.earned_in_game_id == gid))
    session.exec(delete(GoldLedger).where(GoldLedger.game_id == gid))
    session.exec(delete(PoolEvent).where(PoolEvent.game_id == gid))
    session.exec(delete(SpinAssignment).where(SpinAssignment.game_id == gid))
    session.exec(delete(LiveGame).where(LiveGame.game_id == gid))
    session.flush()
    session.delete(game)
    session.flush()


def recount(session: Session, run: Run) -> None:
    """Wins, the current streak and the best streak, counted again from the run's games."""
    wins = streak = best = 0
    for status in session.exec(
        select(ChallengeGame.status).where(ChallengeGame.run_id == run.id).order_by(col(ChallengeGame.id))
    ).all():
        if status == "won":
            wins += 1
            streak += 1
            best = max(best, streak)
        elif status == "lost":
            streak = 0
    run.win_count, run.current_streak, run.best_streak = wins, streak, best
    session.add(run)
    session.flush()


def apply(session: Session, p: Plan) -> dict:
    for r, _ in p.other_runs:
        rules.delete_run(session, r)
    finished = False
    for g in p.games:
        finished |= g.status in ("won", "lost")
        delete_game(session, g)
    if p.run is not None and finished:
        recount(session, p.run)
    return {"runs_deleted": len(p.other_runs), "games_deleted": len(p.games), "kept": sorted(p.blocked)}
