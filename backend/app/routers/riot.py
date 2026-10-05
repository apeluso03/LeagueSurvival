from fastapi import APIRouter, Depends
from sqlmodel import Session, col, select

from app.config import get_settings
from app.db import get_session
from app.models import Player
from app.routers.common import get_app_settings
from app.schemas import RiotStatusOut, SyncOut
from app.services import matcher, sync
from app.services.riot_client import RiotClient, RiotError, RiotNotConfigured

router = APIRouter(prefix="/api", tags=["riot"])


@router.get("/riot/status", response_model=RiotStatusOut)
async def riot_status(check: bool = False, session: Session = Depends(get_session)):
    """API key and last sync info. With check=true, makes one Riot call to test the key."""
    settings = get_app_settings(session)
    key_set = bool(get_settings().riot_api_key)
    valid, message = None, None
    if not key_set:
        message = RiotNotConfigured().args[0]
    elif check:
        platform = session.exec(select(Player.platform).where(col(Player.puuid).is_not(None))).first() or "na1"
        try:
            async with RiotClient() as client:
                await client.platform_status(platform)
            valid = True
        except RiotError as e:
            valid, message = False, str(e)
    return RiotStatusOut(
        key_set=key_set,
        key_valid=valid,
        message=message,
        last_sync_at=settings.last_sync_at,
        last_sync_error=settings.last_sync_error,
    )


@router.post("/sync", response_model=SyncOut)
async def sync_now(session: Session = Depends(get_session)):
    """Import recent matches for every linked player, then try to resolve pending games."""
    settings = get_app_settings(session)
    async with RiotClient() as client:
        result = await sync.sync_all(session, client)
    outcomes = matcher.run_matcher(session) if settings.challenge_mode else []
    session.commit()
    return SyncOut(**result.__dict__, games=[o.__dict__ for o in outcomes])
