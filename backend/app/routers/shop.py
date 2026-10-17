"""Gold and shop endpoints (SPEC 11)."""

from collections import Counter

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, col, select

from app.db import get_session
from app.models import InventoryItem, Player, Run, User
from app.routers.access import can_act_for, current_user, require_act_for, require_manager
from app.routers.common import contract_out, get_or_404, item_out
from app.schemas import (
    GoldAdjustIn,
    GoldOut,
    InventoryItemOut,
    ItemUseIn,
    LedgerRowOut,
    PlayerEconomyOut,
    PurchaseIn,
    PurchaseOut,
    ShopOut,
)
from app.services import contracts, economy, shop, shop_config

router = APIRouter(prefix="/api", tags=["shop"])


def _run_and_player(session: Session, run_id: int, player_id: int, user: User) -> Run:
    """The run, if `user` may see and spend this player's gold: their own player, or the run's owner."""
    run = get_or_404(session, Run, run_id, "Run")
    get_or_404(session, Player, player_id, "Player")
    require_act_for(user, run, player_id)
    return run


@router.get("/runs/{run_id}/shop", response_model=ShopOut)
def get_shop(run_id: int, session: Session = Depends(get_session)):
    return shop.catalog(session, get_or_404(session, Run, run_id, "Run"))


@router.patch("/runs/{run_id}/shop-config", response_model=ShopOut)
def update_shop_config(run_id: int, body: dict, user: User = Depends(current_user), session: Session = Depends(get_session)):
    """Override prices, gold rates, contract targets/payouts or the blacklist percentage for a run."""
    run = get_or_404(session, Run, run_id, "Run")
    require_manager(user, run)
    try:
        clean = shop_config.validate_patch(body)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    merged = dict(run.shop_config or {})
    for section, values in clean.items():
        merged[section] = {**merged.get(section, {}), **values} if isinstance(values, dict) else values
    run.shop_config = merged
    session.add(run)
    session.commit()
    return shop.catalog(session, run)


@router.get("/runs/{run_id}/economy", response_model=list[PlayerEconomyOut])
def run_economy(run_id: int, user: User = Depends(current_user), session: Session = Depends(get_session)):
    """Gold and item status for every player in one call (Wheels and Shop tabs). Players only get
    their own row; the run's owner gets everyone's."""
    run = get_or_404(session, Run, run_id, "Run")
    players = [
        p for p in session.exec(select(Player).order_by(col(Player.display_name))).all() if can_act_for(user, run, p.id)
    ]
    items = session.exec(select(InventoryItem).where(InventoryItem.run_id == run.id)).all()
    out = []
    for p in players:
        mine = [i for i in items if i.player_id == p.id]
        armed = next((i for i in mine if i.type == "blacklist" and i.status == "armed"), None)
        pending = contracts.pending_for(session, run.id, p.id)
        out.append(
            PlayerEconomyOut(
                player_id=p.id,
                **economy.totals(session, run.id, p.id),
                unused=dict(Counter(i.type for i in mine if i.status == "unused")),
                armed_blacklist=armed.target.get("champion_ids") if armed else None,
                active_contract=contract_out(pending[0][0]) if pending else None,
            )
        )
    return out


@router.get("/runs/{run_id}/players/{player_id}/gold", response_model=GoldOut)
def player_gold(run_id: int, player_id: int, user: User = Depends(current_user), session: Session = Depends(get_session)):
    _run_and_player(session, run_id, player_id, user)
    rows = economy.ledger(session, run_id, player_id)
    return GoldOut(**economy.totals(session, run_id, player_id), ledger=[LedgerRowOut(**r.model_dump()) for r in rows])


@router.post("/runs/{run_id}/players/{player_id}/gold/adjust", response_model=GoldOut)
def adjust_gold(
    run_id: int, player_id: int, body: GoldAdjustIn, user: User = Depends(current_user), session: Session = Depends(get_session)
):
    run = _run_and_player(session, run_id, player_id, user)
    require_manager(user, run)
    shop.adjust_gold(session, run, player_id, body.amount, body.note)
    session.commit()
    return player_gold(run_id, player_id, user, session)


@router.get("/runs/{run_id}/players/{player_id}/inventory", response_model=list[InventoryItemOut])
def player_inventory(run_id: int, player_id: int, user: User = Depends(current_user), session: Session = Depends(get_session)):
    _run_and_player(session, run_id, player_id, user)
    return [item_out(i, c) for i, c in shop.inventory(session, run_id, player_id)]


@router.post("/runs/{run_id}/players/{player_id}/purchase", response_model=PurchaseOut)
def purchase(
    run_id: int, player_id: int, body: PurchaseIn, user: User = Depends(current_user), session: Session = Depends(get_session)
):
    run = _run_and_player(session, run_id, player_id, user)
    item, contract = shop.purchase(session, run, player_id, body.type)
    session.commit()
    session.refresh(item)  # committed objects are expired; reload before serializing
    if contract:
        session.refresh(contract)
    return PurchaseOut(item=item_out(item, contract), balance=economy.balance(session, run_id, player_id))


@router.post("/items/{item_id}/use", response_model=InventoryItemOut)
def use_item(item_id: int, body: ItemUseIn, user: User = Depends(current_user), session: Session = Depends(get_session)):
    item = get_or_404(session, InventoryItem, item_id, "Item")
    require_act_for(user, session.get(Run, item.run_id), item.player_id)
    shop.use_item(session, item, body.model_dump(exclude_none=True))
    session.commit()
    session.refresh(item)
    return item_out(item)
