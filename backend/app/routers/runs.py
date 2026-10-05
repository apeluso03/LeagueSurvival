from fastapi import APIRouter, Body, Depends
from sqlmodel import Session, col, select

from app.db import get_session
from app.models import Champion, PoolEntry, ReviveToken, Run
from app.routers.common import game_out, get_app_settings, get_or_404, run_out
from app.schemas import AssignmentOut, PoolEntryOut, RunIn, RunOut, SpinIn, SpinOut
from app.services import rules

router = APIRouter(prefix="/api/runs", tags=["runs"])


@router.get("", response_model=list[RunOut])
def list_runs(session: Session = Depends(get_session)):
    runs = session.exec(select(Run).order_by(col(Run.id).desc())).all()
    return [run_out(session, r) for r in runs]


@router.post("", response_model=RunOut, status_code=201)
def create_run(body: RunIn, session: Session = Depends(get_session)):
    run = rules.create_run(session, body.name, body.options_per_player, body.champion_ids)
    settings = get_app_settings(session)
    settings.active_run_id = run.id
    session.add(settings)
    session.commit()
    return run_out(session, run)


@router.get("/{run_id}", response_model=RunOut)
def get_run(run_id: int, session: Session = Depends(get_session)):
    return run_out(session, get_or_404(session, Run, run_id, "Run"))


@router.post("/{run_id}/end", response_model=RunOut)
def end_run(run_id: int, session: Session = Depends(get_session)):
    run = rules.end_run(session, get_or_404(session, Run, run_id, "Run"))
    session.commit()
    return run_out(session, run)


@router.get("/{run_id}/pool", response_model=list[PoolEntryOut])
def get_pool(run_id: int, include_eliminated: bool = True, session: Session = Depends(get_session)):
    get_or_404(session, Run, run_id, "Run")
    query = (
        select(PoolEntry, Champion)
        .join(Champion, col(Champion.id) == col(PoolEntry.champion_id))
        .where(PoolEntry.run_id == run_id)
        .order_by(col(Champion.name))
    )
    if not include_eliminated:
        query = query.where(PoolEntry.status == "alive")
    return [
        PoolEntryOut(**entry.model_dump(), **champ.model_dump(exclude={"id"}))
        for entry, champ in session.exec(query).all()
    ]


@router.post("/{run_id}/pool/{champion_id}/eliminate", response_model=RunOut)
def eliminate(run_id: int, champion_id: str, session: Session = Depends(get_session)):
    run = get_or_404(session, Run, run_id, "Run")
    rules.manual_eliminate(session, run, champion_id)
    session.commit()
    return run_out(session, run)


@router.post("/{run_id}/pool/{champion_id}/revive", response_model=RunOut)
def revive(
    run_id: int,
    champion_id: str,
    token_id: int | None = Body(default=None, embed=True),
    session: Session = Depends(get_session),
):
    """Revive with a token when token_id is given, otherwise a logged manual fix."""
    run = get_or_404(session, Run, run_id, "Run")
    if token_id is None:
        rules.manual_revive(session, run, champion_id)
    else:
        token = get_or_404(session, ReviveToken, token_id, "Token")
        if token.run_id != run_id:
            raise rules.RuleError("That token belongs to a different run")
        rules.use_token(session, token, champion_id)
    session.commit()
    return run_out(session, run)


@router.post("/{run_id}/spins", response_model=SpinOut)
def spin(run_id: int, body: SpinIn, session: Session = Depends(get_session)):
    """Spin for the given players. With challenge mode off, this is a practice spin that saves nothing."""
    run = get_or_404(session, Run, run_id, "Run")
    settings = get_app_settings(session)

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
