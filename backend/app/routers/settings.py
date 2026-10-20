"""A group's settings (group owner), plus the site-wide build crawler settings (site admin)."""

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from app.config import get_settings
from app.db import get_session
from app.models import AppSettings, SiteSettings
from app.routers.access import Ctx, get_run, group_ctx
from app.routers.common import get_app_settings
from app.schemas import SettingsOut, SettingsPatch
from app.services import auth, rules

router = APIRouter(prefix="/api/settings", tags=["settings"])

SITE_FIELDS = {"meta_crawl", "meta_platform", "meta_region"}


def settings_out(s: AppSettings, site: SiteSettings) -> SettingsOut:
    return SettingsOut(
        **s.model_dump(exclude={"id", "group_id"}),
        riot_api_key_set=bool(get_settings().riot_api_key),
        meta_crawl=site.meta_crawl,
        meta_platform=site.meta_platform,
        meta_region=site.meta_region,
    )


@router.get("", response_model=SettingsOut)
def read_settings(ctx: Ctx = Depends(group_ctx), session: Session = Depends(get_session)):
    return settings_out(get_app_settings(session, ctx.group_id), auth.site_settings(session))


@router.patch("", response_model=SettingsOut)
def update_settings(body: SettingsPatch, ctx: Ctx = Depends(group_ctx), session: Session = Depends(get_session)):
    changes = body.model_dump(exclude_unset=True, exclude={"void_pending"})
    site_changes = {k: v for k, v in changes.items() if k in SITE_FIELDS}
    group_changes = {k: v for k, v in changes.items() if k not in SITE_FIELDS}
    if site_changes and not ctx.user.is_admin:
        raise HTTPException(403, "Only the site admin can change the build crawler")
    if group_changes and not ctx.is_owner:
        raise HTTPException(403, "Only the group's owner can do that")

    s = get_app_settings(session, ctx.group_id)
    if group_changes.get("active_run_id") is not None:
        get_run(session, ctx, group_changes["active_run_id"])
    turning_off = group_changes.get("challenge_mode") is False and s.challenge_mode
    if turning_off and body.void_pending and s.active_run_id:
        game = rules.pending_game(session, s.active_run_id)
        if game:
            rules.apply_result(session, game, "void", void_reason="challenge mode turned off")
    for field, value in group_changes.items():
        setattr(s, field, value)
    session.add(s)

    site = auth.site_settings(session)
    for field, value in site_changes.items():
        setattr(site, field, value)
    session.add(site)
    session.commit()
    session.refresh(s)
    return settings_out(s, site)
