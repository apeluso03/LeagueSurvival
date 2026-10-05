import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlmodel import Session, select

from app.config import BACKEND_DIR, get_settings
from app.db import engine
from app.models import Champion
from app.routers import champions, games, players, runs, settings, tokens
from app.services import ddragon
from app.services.rules import RuleError

log = logging.getLogger("uvicorn.error")


def run_migrations() -> None:
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    command.upgrade(cfg, "head")


async def import_champions_if_empty() -> None:
    with Session(engine) as session:
        if session.exec(select(Champion.id)).first():
            return
        try:
            count = await ddragon.refresh_champions(session)
            session.commit()
            log.info("Imported %d champions from Data Dragon", count)
        except Exception as e:  # noqa: BLE001 - startup must not fail when offline
            log.warning("Could not import champions from Data Dragon: %s", e)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if get_settings().startup_tasks:
        run_migrations()
        await import_champions_if_empty()
    yield


app = FastAPI(title="LoL Survival Tracker", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origin_list,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(RuleError)
async def rule_error_handler(_request: Request, exc: RuleError):
    return JSONResponse(status_code=exc.status, content={"detail": str(exc)})


@app.get("/api/health")
def health():
    return {"ok": True}


for module in (settings, players, champions, runs, games, tokens):
    app.include_router(module.router)
