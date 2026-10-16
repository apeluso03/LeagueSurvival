from fastapi import APIRouter, Depends
from sqlmodel import Session, col, select

from app.db import get_session
from app.models import ReviveToken, Run, User
from app.routers.access import current_user, require_act_for
from app.routers.common import get_or_404
from app.schemas import TokenUseIn
from app.services import rules

router = APIRouter(prefix="/api/tokens", tags=["tokens"])


@router.get("", response_model=list[ReviveToken])
def list_tokens(
    run_id: int | None = None,
    player_id: int | None = None,
    unused_only: bool = False,
    session: Session = Depends(get_session),
):
    query = select(ReviveToken).order_by(col(ReviveToken.id))
    if run_id is not None:
        query = query.where(ReviveToken.run_id == run_id)
    if player_id is not None:
        query = query.where(ReviveToken.player_id == player_id)
    if unused_only:
        query = query.where(col(ReviveToken.used_at).is_(None))
    return session.exec(query).all()


@router.post("/{token_id}/use", response_model=ReviveToken)
def use_token(token_id: int, body: TokenUseIn, user: User = Depends(current_user), session: Session = Depends(get_session)):
    token = get_or_404(session, ReviveToken, token_id, "Token")
    require_act_for(user, session.get(Run, token.run_id), token.player_id)
    rules.use_token(session, token, body.champion_id)
    session.commit()
    session.refresh(token)
    return token
