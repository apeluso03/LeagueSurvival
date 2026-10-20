"""Live game tracker (services/live.py, jobs/live_tracker.py)."""

from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from app.db import get_session
from app.models import Champion, LiveGame
from app.routers.access import Ctx, get_game, group_ctx
from app.services import live, meta

router = APIRouter(prefix="/api", tags=["live"])


async def _static(session: Session) -> dict | None:
    version = session.exec(select(Champion.ddragon_version)).first()
    if not version:
        return None
    try:
        return await meta.load_static(version)
    except Exception:  # noqa: BLE001 - names and icons are optional
        return None


@router.get("/live")
async def current_live(ctx: Ctx = Depends(group_ctx), session: Session = Depends(get_session)):
    """The live game for the group's pending challenge game, if one has been found."""
    game = live.pending_game(session, ctx.group_id)
    row = session.get(LiveGame, game.id) if game else None
    return {"game_id": game.id if game else None, "live": live.live_out(session, row, await _static(session))}


@router.get("/games/{game_id}/live")
async def game_live(game_id: int, ctx: Ctx = Depends(group_ctx), session: Session = Depends(get_session)):
    get_game(session, ctx, game_id)
    return {"game_id": game_id, "live": live.live_out(session, session.get(LiveGame, game_id), await _static(session))}
