"""Trophies, Hall of Shame, monthly Wrapped, and the high-elo meta (comp suggestions)."""

from dataclasses import asdict
from datetime import UTC, datetime
from typing import Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.db import get_session
from app.models import Champion, User
from app.routers.access import Ctx, get_run, group_ctx, require_admin
from app.services import achievements, meta, shame

router = APIRouter(prefix="/api", tags=["fun"])


@router.get("/achievements")
def get_achievements(ctx: Ctx = Depends(group_ctx), session: Session = Depends(get_session)):
    return achievements.report(session, ctx.group_id)


@router.get("/shame")
def get_shame(run_id: int | None = None, ctx: Ctx = Depends(group_ctx), session: Session = Depends(get_session)):
    if run_id is not None:
        get_run(session, ctx, run_id)
    return shame.hall_of_shame(session, ctx.group_id, run_id)


@router.get("/wrapped")
def get_wrapped(month: str | None = None, ctx: Ctx = Depends(group_ctx), session: Session = Depends(get_session)):
    """A month's Wrapped ("2026-10"). Defaults to the latest month with games."""
    if month is None:
        months = shame.available_months(session, ctx.group_id)
        month = months[0] if months else datetime.now(UTC).strftime("%Y-%m")
    try:
        shame.month_bounds(month)
    except (ValueError, TypeError) as e:
        raise HTTPException(400, "Month must look like 2026-10") from e
    return shame.wrapped(session, month, ctx.group_id)


# --- meta ---


class CompIn(BaseModel):
    champion_ids: list[str] = Field(min_length=1, max_length=5)
    # Never suggest banning these (everyone's options, so a backup isn't banned away).
    exclude: list[str] = Field(default_factory=list, max_length=30)
    # Champion id -> the role it's really in (live game or set by hand); the build follows it.
    roles: dict[str, Literal["TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY"]] = Field(default_factory=dict, max_length=5)


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
    result = meta.suggest_comp(session, body.champion_ids, static, exclude=body.exclude, roles=body.roles)
    return {**result, "picks": [asdict(p) for p in result["picks"]]}
