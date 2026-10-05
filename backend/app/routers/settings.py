from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.config import get_settings
from app.db import get_session
from app.models import AppSettings, Run
from app.routers.common import get_app_settings, get_or_404
from app.schemas import SettingsOut, SettingsPatch
from app.services import rules

router = APIRouter(prefix="/api/settings", tags=["settings"])


def settings_out(s: AppSettings) -> SettingsOut:
    return SettingsOut(**s.model_dump(), riot_api_key_set=bool(get_settings().riot_api_key))


@router.get("", response_model=SettingsOut)
def read_settings(session: Session = Depends(get_session)):
    return settings_out(get_app_settings(session))


@router.patch("", response_model=SettingsOut)
def update_settings(body: SettingsPatch, session: Session = Depends(get_session)):
    s = get_app_settings(session)
    changes = body.model_dump(exclude_unset=True, exclude={"void_pending"})
    if changes.get("active_run_id") is not None:
        get_or_404(session, Run, changes["active_run_id"], "Run")

    turning_off = changes.get("challenge_mode") is False and s.challenge_mode
    if turning_off and body.void_pending and s.active_run_id:
        game = rules.pending_game(session, s.active_run_id)
        if game:
            rules.apply_result(session, game, "void", void_reason="challenge mode turned off")

    for field, value in changes.items():
        setattr(s, field, value)
    session.add(s)
    session.commit()
    session.refresh(s)
    return settings_out(s)
