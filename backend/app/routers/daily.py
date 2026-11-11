"""Daily Statline, the daily guessing game (services/daily.py, SPEC 20)."""

from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlmodel import Session

from app.db import get_session
from app.routers.access import Ctx, group_ctx
from app.services import daily

router = APIRouter(prefix="/api/daily", tags=["daily"])


@router.get("")
def today(ctx: Ctx = Depends(group_ctx), session: Session = Depends(get_session)):
    """Today's puzzle for your group, with your guesses so far (made on first look)."""
    puzzle = daily.puzzle_for(session, ctx.group_id)
    session.commit()
    if puzzle is None:
        return {"available": False}
    return {"available": True, **daily.view(session, puzzle, ctx.user)}


class GuessIn(BaseModel):
    question: Literal["result", "pilot", "kda", "grade"]
    value: str | int | list[int]


@router.post("/guess")
def make_guess(body: GuessIn, ctx: Ctx = Depends(group_ctx), session: Session = Depends(get_session)):
    puzzle = daily.puzzle_for(session, ctx.group_id)
    if puzzle is None:
        return {"available": False}
    daily.guess(session, puzzle, ctx.user, body.question, body.value)
    session.commit()
    return {"available": True, **daily.view(session, puzzle, ctx.user)}
