from dataclasses import asdict

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlmodel import Session, col, select

from app.db import get_session
from app.models import Champion, InventoryItem, Player, PoolEntry, PoolEvent, ReviveToken, Run
from app.routers.access import Ctx, get_player, get_run, group_ctx, require_act_for, require_manager, require_owner
from app.routers.common import game_out, get_app_settings, run_out
from app.schemas import AssignmentOut, PoolEntryOut, RunIn, RunOut, SpinIn, SpinOut
from app.services import recap, rules, stats

router = APIRouter(prefix="/api/runs", tags=["runs"])


@router.get("", response_model=list[RunOut])
def list_runs(ctx: Ctx = Depends(group_ctx), session: Session = Depends(get_session)):
    runs = session.exec(select(Run).where(Run.group_id == ctx.group_id).order_by(col(Run.id).desc())).all()
    return [run_out(session, r) for r in runs]


@router.post("", response_model=RunOut, status_code=201)
def create_run(body: RunIn, ctx: Ctx = Depends(require_owner), session: Session = Depends(get_session)):
    run = rules.create_run(session, body.name, body.options_per_player, body.champion_ids, group_id=ctx.group_id)
    run.owner_user_id = ctx.user.id
    if body.owner_player_id is not None:
        get_player(session, ctx, body.owner_player_id)
        run.owner_player_id = body.owner_player_id
    settings = get_app_settings(session, ctx.group_id)
    settings.active_run_id = run.id
    session.add(settings)
    session.commit()
    return run_out(session, run)


@router.get("/{run_id}", response_model=RunOut)
def read_run(run_id: int, ctx: Ctx = Depends(group_ctx), session: Session = Depends(get_session)):
    return run_out(session, get_run(session, ctx, run_id))


@router.delete("/{run_id}", status_code=204)
def delete_run(run_id: int, ctx: Ctx = Depends(group_ctx), session: Session = Depends(get_session)):
    """Permanently delete a run and everything in it (games, pool, gold, items)."""
    run = get_run(session, ctx, run_id)
    require_manager(ctx, run)
    rules.delete_run(session, run)
    session.commit()


@router.post("/{run_id}/end", response_model=RunOut)
def end_run(run_id: int, ctx: Ctx = Depends(group_ctx), session: Session = Depends(get_session)):
    run = get_run(session, ctx, run_id)
    require_manager(ctx, run)
    run = rules.end_run(session, run)
    session.commit()
    return run_out(session, run)


@router.get("/{run_id}/pool", response_model=list[PoolEntryOut])
def get_pool(
    run_id: int, include_eliminated: bool = True, ctx: Ctx = Depends(group_ctx), session: Session = Depends(get_session)
):
    get_run(session, ctx, run_id)
    query = (
        select(PoolEntry, Champion)
        .join(Champion, col(Champion.id) == col(PoolEntry.champion_id))
        .where(PoolEntry.run_id == run_id)
        .order_by(col(Champion.name))
    )
    if not include_eliminated:
        query = query.where(PoolEntry.status == "alive")
    shield_owner = {
        i.id: i.player_id
        for i in session.exec(
            select(InventoryItem).where(InventoryItem.run_id == run_id, InventoryItem.type == "shield")
        ).all()
    }
    return [
        PoolEntryOut(
            **entry.model_dump(),
            **champ.model_dump(exclude={"id"}),
            shield_player_id=shield_owner.get(entry.shield_item_id) if entry.shield_item_id else None,
        )
        for entry, champ in session.exec(query).all()
    ]


@router.get("/{run_id}/recap")
def run_recap(run_id: int, ctx: Ctx = Depends(group_ctx), session: Session = Depends(get_session)):
    """Everything the run recap page shows: totals, the win/loss timeline, per-player lines and awards."""
    return recap.run_recap(session, get_run(session, ctx, run_id))


@router.get("/{run_id}/champion-lines")
def champion_lines(run_id: int, ctx: Ctx = Depends(group_ctx), session: Session = Depends(get_session)):
    """Short numbers for every champion card on the Pool tab, in one request."""
    get_run(session, ctx, run_id)
    return {cid: asdict(line) for cid, line in stats.run_champion_lines(session, run_id).items()}


@router.post("/{run_id}/pool/{champion_id}/eliminate", response_model=RunOut)
def eliminate(run_id: int, champion_id: str, ctx: Ctx = Depends(group_ctx), session: Session = Depends(get_session)):
    run = get_run(session, ctx, run_id)
    require_manager(ctx, run)
    rules.manual_eliminate(session, run, champion_id)
    session.commit()
    return run_out(session, run)


@router.post("/{run_id}/pool/{champion_id}/revive", response_model=RunOut)
def revive(
    run_id: int,
    champion_id: str,
    token_id: int | None = Body(default=None, embed=True),
    ctx: Ctx = Depends(group_ctx),
    session: Session = Depends(get_session),
):
    """Revive with a token when token_id is given, otherwise a logged manual fix (run owner only)."""
    run = get_run(session, ctx, run_id)
    if token_id is None:
        require_manager(ctx, run)
        rules.manual_revive(session, run, champion_id)
    else:
        token = session.get(ReviveToken, token_id)
        if token is None or token.run_id != run_id:
            raise HTTPException(404, f"Token {token_id} not found")
        require_act_for(ctx, run, token.player_id)
        rules.use_token(session, token, champion_id)
    session.commit()
    return run_out(session, run)


@router.post("/{run_id}/spins", response_model=SpinOut)
def spin(run_id: int, body: SpinIn, ctx: Ctx = Depends(group_ctx), session: Session = Depends(get_session)):
    """Spin for the given players. With challenge mode off, this is a practice spin that saves nothing."""
    run = get_run(session, ctx, run_id)
    require_manager(ctx, run)
    groups = {pid: g for pid, g in session.exec(select(Player.id, Player.group_id).where(col(Player.id).in_(body.player_ids))).all()}
    if any(groups.get(pid) != ctx.group_id for pid in body.player_ids):
        raise HTTPException(404, "One of those players isn't in this group")
    settings = get_app_settings(session, ctx.group_id)

    if settings.challenge_mode:
        game = rules.create_spin(session, run, body.player_ids)
        result = SpinOut(practice=False, game=game_out(session, game), assignments=[])
        result.assignments = result.game.assignments
    else:
        options = rules.draw_options(session, run, body.player_ids)
        result = SpinOut(
            practice=True,
            game=None,
            assignments=[AssignmentOut(player_id=p, options=o) for p, o in zip(body.player_ids, options)],
        )

    settings.last_used_player_ids = list(body.player_ids)
    session.add(settings)
    session.commit()
    return result


@router.get("/{run_id}/events", response_model=list[PoolEvent])
def pool_events(run_id: int, ctx: Ctx = Depends(group_ctx), session: Session = Depends(get_session)):
    """The run's pool activity log, newest first: eliminations, revives (token or manual) and manual edits."""
    get_run(session, ctx, run_id)
    return session.exec(select(PoolEvent).where(PoolEvent.run_id == run_id).order_by(col(PoolEvent.id).desc())).all()
