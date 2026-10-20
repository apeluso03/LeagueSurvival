from dataclasses import asdict

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, col, select

from app.db import get_session
from app.models import Champion, User
from app.routers.access import Ctx, get_run, group_ctx, require_admin
from app.routers.common import get_or_404
from app.services import ddragon, stats

router = APIRouter(prefix="/api/champions", tags=["champions"])


@router.get("", response_model=list[Champion])
def list_champions(session: Session = Depends(get_session)):
    return session.exec(select(Champion).order_by(col(Champion.name))).all()


@router.post("/refresh")
async def refresh_champions(_: User = Depends(require_admin), session: Session = Depends(get_session)):
    try:
        count = await ddragon.refresh_champions(session)
    except httpx.HTTPError as e:
        raise HTTPException(502, f"Could not reach Data Dragon: {e}") from e
    session.commit()
    return {"count": count}


@router.get("/{champion_id}/stats")
def champion_stats(
    champion_id: str, run_id: int | None = None, ctx: Ctx = Depends(group_ctx), session: Session = Depends(get_session)
):
    """Everything the Pool tab shows on a champion's card (SPEC 17.4), for this group."""
    champion = get_or_404(session, Champion, champion_id, "Champion")
    if run_id is not None:
        get_run(session, ctx, run_id)
    return asdict(stats.champion_report(session, champion, run_id, ctx.group_id))
