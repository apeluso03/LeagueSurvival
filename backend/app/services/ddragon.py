"""Champion list and images from Data Dragon (no API key needed)."""

import httpx
from sqlmodel import Session

from app.config import get_settings
from app.models import Champion


def parse_champions(data: dict, version: str, base_url: str) -> list[Champion]:
    champs = []
    for c in data["data"].values():
        champs.append(
            Champion(
                id=c["id"],
                key=int(c["key"]),
                name=c["name"],
                title=c.get("title", ""),
                tags=list(c.get("tags", [])),
                image_url=f"{base_url}/cdn/{version}/img/champion/{c['image']['full']}",
                ddragon_version=version,
            )
        )
    return champs


async def fetch_champions(client: httpx.AsyncClient | None = None) -> list[Champion]:
    base = get_settings().ddragon_base_url
    own_client = client is None
    client = client or httpx.AsyncClient(timeout=20)
    try:
        versions = (await client.get(f"{base}/api/versions.json")).raise_for_status().json()
        version = versions[0]
        data = (
            await client.get(f"{base}/cdn/{version}/data/en_US/champion.json")
        ).raise_for_status().json()
        return parse_champions(data, version, base)
    finally:
        if own_client:
            await client.aclose()


def upsert_champions(session: Session, champions: list[Champion]) -> int:
    for champ in champions:
        session.merge(champ)
    session.flush()
    return len(champions)


async def refresh_champions(session: Session) -> int:
    return upsert_champions(session, await fetch_champions())
