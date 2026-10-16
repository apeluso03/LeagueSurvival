"""Trophies, Hall of Shame, monthly Wrapped, and the high-elo meta (comp suggestions)."""

from dataclasses import asdict
from datetime import UTC, datetime

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.db import get_session
from app.models import Champion, Run, User
from app.routers.access import require_admin
from app.routers.common import get_or_404
from app.services import achievements, meta, shame

router = APIRouter(prefix="/api", tags=["fun"])


@router.get("/achievements")
def get_achievements(session: Session = Depends(get_session)):
    return achievements.report(session)


@router.get("/shame")
def get_shame(run_id: int | None = None, session: Session = Depends(get_session)):
    if run_id is not None:
        get_or_404(session, Run, run_id, "Run")
    return shame.hall_of_shame(session, run_id)


@router.get("/wrapped")
def get_wrapped(month: str | None = None, session: Session = Depends(get_session)):
    """A month's Wrapped ("2026-10"). Defaults to the latest month with games."""
    if month is None:
        months = shame.available_months(session)
        month = months[0] if months else datetime.now(UTC).strftime("%Y-%m")
    try:
        shame.month_bounds(month)
    except (ValueError, TypeError) as e:
        raise HTTPException(400, "Month must look like 2026-10") from e
    return shame.wrapped(session, month)


# --- meta ---


class CompIn(BaseModel):
    champion_ids: list[str] = Field(min_length=1, max_length=5)


@router.get("/meta/status")
def meta_status(session: Session = Depends(get_session)):
    return meta.status(session)


@router.post("/meta/positions/refresh")
async def refresh_positions(_: User = Depends(require_admin), session: Session = Depends(get_session)):
    try:
        count = await meta.refresh_positions(session)
    except httpx.HTTPError as e:
        raise HTTPException(502, f"Could not reach Meraki Analytics: {e}") from e
    session.commit()
    return {"count": count}


@router.post("/comp")
async def suggest_comp(body: CompIn, session: Session = Depends(get_session)):
    """Suggested roles for the rolled champions, with high-elo runes and core items for each."""
    version = session.exec(select(Champion.ddragon_version)).first()
    static = None
    if version:
        try:
            static = await meta.load_static(version)
        except httpx.HTTPError:
            static = None  # names and icons are optional; ids still work
    result = meta.suggest_comp(session, body.champion_ids, static)
    return {**result, "picks": [asdict(p) for p in result["picks"]]}
