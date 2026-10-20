from dataclasses import asdict

from fastapi import APIRouter, Depends
from sqlmodel import Session, col, select

from app.db import get_session
from app.models import Player, Run
from app.routers.access import Ctx, can_act_for, get_player, get_run, group_ctx
from app.schemas import PlayerStatsOut
from app.services import stats

router = APIRouter(prefix="/api/stats", tags=["stats"])


@router.get("/players", response_model=list[PlayerStatsOut])
def all_player_stats(
    run_id: int | None = None,
    challenge_only: bool = True,
    ctx: Ctx = Depends(group_ctx),
    session: Session = Depends(get_session),
):
    if run_id is not None:
        get_run(session, ctx, run_id)
    ids = list(session.exec(select(Player.id).where(Player.group_id == ctx.group_id).order_by(col(Player.display_name))).all())
    return [_private_gold(session, ctx, run_id, asdict(s)) for s in stats.player_stats(session, ids, run_id, challenge_only)]


@router.get("/players/{player_id}", response_model=PlayerStatsOut)
def one_player_stats(
    player_id: int,
    run_id: int | None = None,
    challenge_only: bool = True,
    ctx: Ctx = Depends(group_ctx),
    session: Session = Depends(get_session),
):
    get_player(session, ctx, player_id)
    if run_id is not None:
        get_run(session, ctx, run_id)
    return _private_gold(session, ctx, run_id, asdict(stats.player_stats(session, [player_id], run_id, challenge_only)[0]))


def _private_gold(session: Session, ctx: Ctx, run_id: int | None, row: dict) -> dict:
    """Gold earned and spent are public stats; a balance is only shown to its player (and the run owner)."""
    run = session.get(Run, run_id) if run_id is not None else None
    if run is None or not can_act_for(ctx, run, row["player_id"]):
        row["gold_balance"] = None
    return row
