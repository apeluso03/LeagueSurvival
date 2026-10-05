import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, col, select

from app.db import get_session
from app.models import Champion
from app.services import ddragon

router = APIRouter(prefix="/api/champions", tags=["champions"])


@router.get("", response_model=list[Champion])
def list_champions(session: Session = Depends(get_session)):
    return session.exec(select(Champion).order_by(col(Champion.name))).all()


@router.post("/refresh")
async def refresh_champions(session: Session = Depends(get_session)):
    try:
        count = await ddragon.refresh_champions(session)
    except httpx.HTTPError as e:
        raise HTTPException(502, f"Could not reach Data Dragon: {e}") from e
    session.commit()
    return {"count": count}
