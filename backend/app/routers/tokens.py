from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, col, select

from app.db import get_session
from app.models import ReviveToken, Run
from app.routers.access import Ctx, get_run, group_ctx, require_act_for
from app.schemas import TokenUseIn
from app.services import rules

router = APIRouter(prefix="/api/tokens", tags=["tokens"])


@router.get("", response_model=list[ReviveToken])
def list_tokens(
    run_id: int | None = None,
    player_id: int | None = None,
    unused_only: bool = False,
    ctx: Ctx = Depends(group_ctx),
    session: Session = Depends(get_session),
):
    query = select(ReviveToken).order_by(col(ReviveToken.id))
    if run_id is not None:
        get_run(session, ctx, run_id)
        query = query.where(ReviveToken.run_id == run_id)
    else:
        query = query.where(col(ReviveToken.run_id).in_(select(Run.id).where(Run.group_id == ctx.group_id)))
    if player_id is not None:
        query = query.where(ReviveToken.player_id == player_id)
    if unused_only:
        query = query.where(col(ReviveToken.used_at).is_(None))
    return session.exec(query).all()


@router.post("/{token_id}/use", response_model=ReviveToken)
def use_token(token_id: int, body: TokenUseIn, ctx: Ctx = Depends(group_ctx), session: Session = Depends(get_session)):
    token = session.get(ReviveToken, token_id)
    if token is None:
        raise HTTPException(404, f"Token {token_id} not found")
    require_act_for(ctx, get_run(session, ctx, token.run_id), token.player_id)
    rules.use_token(session, token, body.champion_id)
    session.commit()
    session.refresh(token)
    return token
