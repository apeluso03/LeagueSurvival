"""Deleting Riot data on request (services/privacy.py): one player (group owner), Riot deletion
lists and everything (site admin)."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session

from app.db import get_session
from app.models import User
from app.routers.access import Ctx, get_player, require_admin, require_owner
from app.services import privacy

router = APIRouter(prefix="/api/privacy", tags=["privacy"])


class ForgetIn(BaseModel):
    # PUUIDs from a Riot deletion request (or any player who asked to be forgotten)
    puuids: list[str] = Field(min_length=1, max_length=5000)


class PurgeIn(BaseModel):
    confirm: str  # must be "DELETE"


@router.post("/players/{player_id}/forget")
def forget_player(player_id: int, ctx: Ctx = Depends(require_owner), session: Session = Depends(get_session)):
    """Delete a player's Riot data: PUUID, Riot ID and match stats. Their challenge history stays."""
    privacy.forget_player(session, get_player(session, ctx, player_id))
    session.commit()
    return {"ok": True}


@router.post("/forget")
def forget_puuids(body: ForgetIn, _: User = Depends(require_admin), session: Session = Depends(get_session)):
    result = privacy.forget_puuids(session, body.puuids)
    session.commit()
    return result


@router.post("/purge")
def purge_all(body: PurgeIn, _: User = Depends(require_admin), session: Session = Depends(get_session)):
    """Delete all Riot data the app holds (e.g. if API access ends). Runs, results and gold stay."""
    if body.confirm != "DELETE":
        raise HTTPException(400, 'Type DELETE to confirm')
    result = privacy.purge_all(session)
    session.commit()
    return result
