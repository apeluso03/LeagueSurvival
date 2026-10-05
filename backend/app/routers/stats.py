from dataclasses import asdict

from fastapi import APIRouter, Depends
from sqlmodel import Session, col, select

from app.db import get_session
from app.models import Player
from app.routers.common import get_or_404
from app.schemas import PlayerStatsOut
from app.services import stats

router = APIRouter(prefix="/api/stats", tags=["stats"])


@router.get("/players", response_model=list[PlayerStatsOut])
def all_player_stats(run_id: int | None = None, challenge_only: bool = True, session: Session = Depends(get_session)):
    ids = list(session.exec(select(Player.id).order_by(col(Player.display_name))).all())
    return [asdict(s) for s in stats.player_stats(session, ids, run_id, challenge_only)]


@router.get("/players/{player_id}", response_model=PlayerStatsOut)
def one_player_stats(
    player_id: int, run_id: int | None = None, challenge_only: bool = True, session: Session = Depends(get_session)
):
    get_or_404(session, Player, player_id, "Player")
    return asdict(stats.player_stats(session, [player_id], run_id, challenge_only)[0])
