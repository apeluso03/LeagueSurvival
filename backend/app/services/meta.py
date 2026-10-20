"""High-elo meta: role, rune and item numbers crawled from Riot match data, and comp suggestions.

The Riot API has no global win rates, so a background job (jobs/crawler.py) builds them:
it walks the Challenger / Grandmaster / Master ranked solo ladders, downloads their recent ranked
games and counts, per champion and role and patch: games and wins, full rune pages, items and
summoner spells, plus how each champion does against every champion on the enemy team.
`suggest_comp` turns those counts (plus Meraki's position list as a fallback) into a suggested role
for each rolled champion with its most played rune page, core items and summoner spells, and
suggests bans: the enemy champions the rolled champions do worst against.
"""

import random
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from itertools import permutations

import httpx
from sqlmodel import Session, col, delete, func, select

from app.config import get_settings
from app.models import (
    SiteSettings,
    Champion,
    MetaChampRole,
    MetaCrawlState,
    MetaItem,
    MetaMatch,
    MetaMatchup,
    MetaRunePage,
    MetaSpells,
)
from app.services.riot_client import RiotError

RANKED_SOLO = 420
ROLES = ("TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY")
ROLE_NAMES = {"TOP": "Top", "JUNGLE": "Jungle", "MIDDLE": "Mid", "BOTTOM": "Bot", "UTILITY": "Support"}
MERAKI_ROLE = {"SUPPORT": "UTILITY"}  # Meraki says SUPPORT where Riot match data says UTILITY
LADDER_TIERS = ("challenger", "grandmaster", "master")
LADDER_SIZE = 400  # players kept per refresh
LADDER_REFRESH = timedelta(hours=12)
MATCHES_PER_PLAYER = 10
MATCH_WINDOW = timedelta(days=7)
MIN_ROLE_GAMES = 20  # below this, roles come from Meraki's position list instead
HIGH_ELO_WEIGHT = 0.8  # with enough games: 80% high-elo role share, 20% Meraki's position list
OFF_ROLE_SHARE = 0.05  # a role played in under 5% of a champ's high-elo games is "off-role"
TRINKETS = {3340, 3363, 3364, 3330, 3513}
FLASH = 4
BACKFILL_BATCH = 10  # matches re-fetched per crawler step to fill in spells and matchups
BAN_COUNT = 5
BAN_PRIOR_GAMES = 10  # matchup win rates are pulled toward the champ's overall rate by this many games


def patch_of(game_version: str) -> str:
    """"16.20.712.1234" -> "16.20"."""
    parts = (game_version or "").split(".")
    return ".".join(parts[:2]) if len(parts) >= 2 else game_version


def rune_page_key(perks: dict) -> str | None:
    """A whole rune page as a string: "primaryStyle:p1,p2,p3,p4|subStyle:s1,s2|shard,shard,shard"."""
    styles = {s.get("description"): s for s in perks.get("styles", [])}
    primary, sub = styles.get("primaryStyle"), styles.get("subStyle")
    if not primary or not sub:
        return None
    stat = perks.get("statPerks", {})
    p = ",".join(str(x["perk"]) for x in primary.get("selections", []))
    s = ",".join(str(x["perk"]) for x in sub.get("selections", []))
    shards = ",".join(str(stat.get(k, 0)) for k in ("offense", "flex", "defense"))
    return f"{primary['style']}:{p}|{sub['style']}:{s}|{shards}"


def _bump(session: Session, model, key: dict, win: bool) -> None:
    row = session.get(model, tuple(key.values()))
    if row is None:
        row = model(**key)
    row.games += 1
    row.wins += int(win)
    session.add(row)


def count_match(session: Session, match: dict) -> bool:
    """Add one ranked solo match to the meta tables. Returns False if it was skipped."""
    meta, info = match.get("metadata", {}), match.get("info", {})
    match_id = meta.get("matchId")
    if not match_id or info.get("queueId") != RANKED_SOLO or session.get(MetaMatch, match_id):
        return False
    if info.get("gameEndedInEarlySurrender") or info.get("gameDuration", 0) < 900:
        return False  # remakes and 15-minute surrenders say little about builds
    patch = patch_of(info.get("gameVersion", ""))
    for p in info.get("participants", []):
        role = p.get("teamPosition")
        if role not in ROLES or not p.get("championId"):
            continue
        base = {"champion_key": p["championId"], "role": role, "patch": patch}
        win = bool(p.get("win"))
        _bump(session, MetaChampRole, base, win)
        page = rune_page_key(p.get("perks", {}))
        if page:
            _bump(session, MetaRunePage, {**base, "page": page}, win)
        for item_id in {p.get(f"item{i}", 0) for i in range(6)}:
            if item_id and item_id not in TRINKETS:
                _bump(session, MetaItem, {**base, "item_id": item_id}, win)
    count_extras(session, info, patch)
    session.add(MetaMatch(match_id=match_id, patch=patch, extras=True))
    session.flush()
    return True


def spells_key(p: dict) -> str | None:
    spells = sorted(x for x in (p.get("summoner1Id"), p.get("summoner2Id")) if x)
    return ",".join(str(x) for x in spells) if len(spells) == 2 else None


def count_extras(session: Session, info: dict, patch: str) -> None:
    """Summoner spells per champion and role, and each champion's record against the enemy team."""
    players = [p for p in info.get("participants", []) if p.get("championId")]
    for p in players:
        win = bool(p.get("win"))
        role, key = p.get("teamPosition"), p["championId"]
        spells = spells_key(p)
        if role in ROLES and spells:
            _bump(session, MetaSpells, {"champion_key": key, "role": role, "patch": patch, "spells": spells}, win)
        for enemy in players:
            if enemy.get("teamId") != p.get("teamId"):
                _bump(session, MetaMatchup, {"champion_key": key, "enemy_key": enemy["championId"], "patch": patch}, win)


def recent_patches(session: Session, n: int = 2) -> list[str]:
    patches = session.exec(select(MetaMatch.patch).distinct()).all()
    return sorted(patches, key=lambda p: tuple(int(x) if x.isdigit() else 0 for x in p.split(".")), reverse=True)[:n]


def prune_old_patches(session: Session, keep: int = 2) -> None:
    keepers = recent_patches(session, keep)
    if not keepers:
        return
    for model in (MetaMatch, MetaChampRole, MetaRunePage, MetaItem, MetaSpells, MetaMatchup):
        session.exec(delete(model).where(col(model.patch).not_in(keepers)))


# --- crawler -----------------------------------------------------------------------------------


def crawl_state(session: Session) -> MetaCrawlState:
    state = session.get(MetaCrawlState, 1)
    if state is None:
        state = MetaCrawlState(id=1)
        session.add(state)
        session.flush()
    return state


async def refresh_ladder(session: Session, client, platform: str, rng: random.Random | None = None) -> int:
    """Fetch the top ranked-solo ladders and queue their players (shuffled). Commits."""
    session.commit()  # never hold the database while waiting on Riot
    puuids: list[str] = []
    for tier in LADDER_TIERS:
        data = await client.league(platform, tier)
        for e in data.get("entries", []):
            if e.get("puuid"):
                puuids.append(e["puuid"])
            elif e.get("summonerId"):  # older responses: look the PUUID up
                summoner = await client.summoner_by_id(platform, e["summonerId"])
                if summoner.get("puuid"):
                    puuids.append(summoner["puuid"])
        if len(puuids) >= LADDER_SIZE:
            break
    (rng or random).shuffle(puuids)
    queued = puuids[:LADDER_SIZE]
    state = crawl_state(session)
    state.puuids = queued
    state.next_index = 0
    state.refreshed_at = datetime.now(UTC)
    prune_old_patches(session)
    session.add(state)
    session.commit()
    return len(queued)  # not state.puuids: reading it after commit would reopen a transaction


async def crawl_step(session: Session, client, pause=None) -> int:
    """Visit the next high-elo player: count their recent ranked games. Returns matches counted.

    SQLite allows one writer at a time, so the crawler commits before every Riot call and after
    every match: it never holds the database while it waits (on Riot, or on `pause`, which spaces
    the calls out so the match poller always has room).
    """
    settings = session.get(SiteSettings, 1) or SiteSettings()
    platform, region = settings.meta_platform, settings.meta_region
    if await backfill_step(session, client, region, pause):
        return 0  # spent this step filling in older matches
    state = crawl_state(session)
    stale = state.refreshed_at is None or datetime.now(UTC) - state.refreshed_at > LADDER_REFRESH
    if stale or state.next_index >= len(state.puuids):
        await refresh_ladder(session, client, platform)
        if pause:
            await pause()
        state = crawl_state(session)
    if not state.puuids:
        session.commit()
        return 0
    puuid = state.puuids[state.next_index]
    state.next_index += 1
    session.add(state)
    session.commit()

    start = int((datetime.now(UTC) - MATCH_WINDOW).timestamp())
    ids = await client.match_ids(region, puuid, start_time=start, count=MATCHES_PER_PLAYER, queue=RANKED_SOLO)
    counted = 0
    for match_id in ids:
        seen = session.get(MetaMatch, match_id) is not None
        session.commit()
        if seen:
            continue
        if pause:
            await pause()
        match = await client.match(region, match_id)
        if count_match(session, match):
            counted += 1
        session.commit()
    state = crawl_state(session)
    state.matches_counted += counted
    state.last_run_at = datetime.now(UTC)
    state.last_error = None
    session.add(state)
    session.commit()
    return counted


def needs_backfill(session: Session, limit: int | None = None) -> list[str]:
    """Matches from the kept patches counted before spells and matchups were tracked."""
    patches = recent_patches(session)
    if not patches:
        return []
    query = select(MetaMatch.match_id).where(MetaMatch.extras == False, col(MetaMatch.patch).in_(patches))  # noqa: E712
    return list(session.exec(query.limit(limit) if limit else query).all())


async def backfill_step(session: Session, client, region: str, pause=None) -> int:
    """Re-fetch a few already-counted matches and add their summoner spells and matchups.
    Returns how many it looked at (0 when there's nothing left to fill in). Commits."""
    ids = needs_backfill(session, BACKFILL_BATCH)
    session.commit()
    for match_id in ids:
        if pause:
            await pause()
        try:
            match = await client.match(region, match_id)
        except RiotError as e:
            if e.status != 404:
                raise
            match = None  # gone from Riot: nothing to add
        row = session.get(MetaMatch, match_id)
        if row is not None and not row.extras:
            info = (match or {}).get("info", {})
            if info:
                count_extras(session, info, row.patch)
            row.extras = True
            session.add(row)
        session.commit()
    return len(ids)


def status(session: Session) -> dict:
    state = session.get(MetaCrawlState, 1)
    settings = session.get(SiteSettings, 1) or SiteSettings()
    patches = recent_patches(session)
    matches = session.exec(select(func.count()).select_from(MetaMatch)).one()
    champs = session.exec(
        select(func.count(func.distinct(MetaChampRole.champion_key))).where(col(MetaChampRole.patch).in_(patches))
    ).one() if patches else 0
    return {
        "enabled": settings.meta_crawl,
        "key_set": bool(get_settings().riot_api_key),
        "platform": settings.meta_platform,
        "patches": patches,
        "matches": matches,
        "champions_covered": champs,
        "ladder_size": len(state.puuids) if state else 0,
        "ladder_position": state.next_index if state else 0,
        "last_run_at": state.last_run_at if state else None,
        "last_error": state.last_error if state else None,
        "backfill_remaining": len(needs_backfill(session)),
    }


# --- static data for names and icons -----------------------------------------------------------

_static: dict[str, dict] = {}


async def load_static(version: str, client: httpx.AsyncClient | None = None) -> dict:
    """Item and rune names/icons from Data Dragon for one version (cached in memory)."""
    if version in _static:
        return _static[version]
    base = get_settings().ddragon_base_url
    own = client is None
    client = client or httpx.AsyncClient(timeout=20)
    try:
        items = (await client.get(f"{base}/cdn/{version}/data/en_US/item.json")).raise_for_status().json()["data"]
        runes = (await client.get(f"{base}/cdn/{version}/data/en_US/runesReforged.json")).raise_for_status().json()
        spells = (await client.get(f"{base}/cdn/{version}/data/en_US/summoner.json")).raise_for_status().json()["data"]
    finally:
        if own:
            await client.aclose()
    perk_names: dict[int, dict] = {}
    for style in runes:
        perk_names[style["id"]] = {"name": style["name"], "icon": f"{base}/cdn/img/{style['icon']}"}
        for slot in style["slots"]:
            for r in slot["runes"]:
                perk_names[r["id"]] = {"name": r["name"], "icon": f"{base}/cdn/img/{r['icon']}"}
    _static[version] = {
        "items": {
            int(k): {
                "name": v["name"],
                "image": f"{base}/cdn/{version}/img/item/{v.get('image', {}).get('full', f'{k}.png')}",
                "total": v.get("gold", {}).get("total", 0),
                "boots": "Boots" in v.get("tags", []),
                "final": not v.get("into"),
            }
            for k, v in items.items()
        },
        "perks": perk_names,
        "spells": {
            int(v["key"]): {"name": v["name"], "icon": f"{base}/cdn/{version}/img/spell/{v['image']['full']}"}
            for v in spells.values()
            if str(v.get("key", "")).isdigit()
        },
        # The game client names spells by Data Dragon id ("SummonerFlash"), not number.
        "spells_by_name": {
            v["id"]: {"name": v["name"], "icon": f"{base}/cdn/{version}/img/spell/{v['image']['full']}"}
            for v in spells.values()
        },
    }
    return _static[version]


SHARD_NAMES = {
    5001: "Health Scaling",
    5005: "Attack Speed",
    5007: "Ability Haste",
    5008: "Adaptive Force",
    5010: "Move Speed",
    5011: "Health",
    5013: "Tenacity and Slow Resist",
}


# --- comp suggestion -------------------------------------------------------------------------


@dataclass
class Pick:
    champion_id: str
    role: str
    role_name: str
    role_source: str  # "high-elo" or "positions"
    role_games: int = 0
    role_win_rate: float | None = None
    off_role: bool = False  # the champ rarely plays this role; the build comes from build_role
    build_role: str | None = None
    runes: dict | None = None
    items: list[dict] = field(default_factory=list)
    boots: dict | None = None
    spells: dict | None = None  # {"spells": [{id, name, icon}, ...], "games", "pick_rate", "win_rate"}


def role_scores(session: Session, champ: Champion, patches: list[str]) -> tuple[dict[str, float], str, dict[str, MetaChampRole]]:
    rows: dict[str, MetaChampRole] = {}
    if patches:
        for r in session.exec(
            select(MetaChampRole).where(MetaChampRole.champion_key == champ.key, col(MetaChampRole.patch).in_(patches))
        ).all():
            agg = rows.setdefault(r.role, MetaChampRole(champion_key=r.champion_key, role=r.role, patch="*"))
            agg.games += r.games
            agg.wins += r.wins
    listed = {role: 0.02 for role in ROLES}
    for i, pos in enumerate(champ.positions or []):
        role = MERAKI_ROLE.get(pos, pos)
        if role in listed:
            listed[role] = max(listed[role], [1.0, 0.6, 0.35, 0.2, 0.1][min(i, 4)])
    total = sum(r.games for r in rows.values())
    if total >= MIN_ROLE_GAMES:
        # Mostly what high elo plays, with the position list breaking ties between unplayed roles.
        share = {role: rows[role].games / total if role in rows else 0.0 for role in ROLES}
        return {r: HIGH_ELO_WEIGHT * share[r] + (1 - HIGH_ELO_WEIGHT) * listed[r] for r in ROLES}, "high-elo", rows
    return listed, "positions", rows


def best_assignment(scores: list[dict[str, float]]) -> list[str]:
    """Give each champion a different role, maximising the total score (at most 5 champions)."""
    n = min(len(scores), len(ROLES))
    best, best_total = list(ROLES[:n]), -1.0
    for roles in permutations(ROLES, n):
        total = sum(scores[i][r] for i, r in enumerate(roles))
        if total > best_total + 1e-9:
            best, best_total = list(roles), total
    return best


def _rate(wins: int, games: int) -> float | None:
    return wins / games if games else None


def build_for(session: Session, champ: Champion, role: str, patches: list[str], static: dict | None) -> tuple[dict | None, list[dict], dict | None]:
    if not patches:
        return None, [], None
    where = (col(MetaRunePage.patch).in_(patches), MetaRunePage.champion_key == champ.key, MetaRunePage.role == role)
    pages: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for r in session.exec(select(MetaRunePage).where(*where)).all():
        pages[r.page][0] += r.games
        pages[r.page][1] += r.wins
    runes = None
    if pages:
        page, (games, wins) = max(pages.items(), key=lambda kv: (kv[1][0], kv[1][1]))
        runes = describe_page(page, games, wins, static)

    items: dict[int, list[int]] = defaultdict(lambda: [0, 0])
    for r in session.exec(
        select(MetaItem).where(col(MetaItem.patch).in_(patches), MetaItem.champion_key == champ.key, MetaItem.role == role)
    ).all():
        items[r.item_id][0] += r.games
        items[r.item_id][1] += r.wins
    role_games = sum(
        r.games
        for r in session.exec(
            select(MetaChampRole).where(
                col(MetaChampRole.patch).in_(patches), MetaChampRole.champion_key == champ.key, MetaChampRole.role == role
            )
        ).all()
    )
    info = (static or {}).get("items", {})

    def item_out(item_id: int, games: int, wins: int) -> dict:
        meta = info.get(item_id, {})
        return {
            "id": item_id,
            "name": meta.get("name", f"Item {item_id}"),
            "image": meta.get("image"),
            "games": games,
            "pick_rate": games / role_games if role_games else None,
            "win_rate": _rate(wins, games),
        }

    ranked = sorted(items.items(), key=lambda kv: -kv[1][0])
    # Core items: finished (nothing builds out of them), 2200g+, not boots. Without item data, top picks.
    core = [
        (i, g, w)
        for i, (g, w) in ranked
        if not info or (info.get(i, {}).get("final") and info.get(i, {}).get("total", 0) >= 2200 and not info.get(i, {}).get("boots"))
    ][:3]
    boots = next(
        ((i, g, w) for i, (g, w) in ranked if info.get(i, {}).get("boots") and info.get(i, {}).get("total", 0) > 300),
        None,
    )
    return runes, [item_out(*c) for c in core], item_out(*boots) if boots else None


def spells_for(session: Session, champ: Champion, role: str, patches: list[str], static: dict | None) -> dict | None:
    """The most played summoner spell pair for a champion in a role, Flash second (on F)."""
    if not patches:
        return None
    pairs: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for r in session.exec(
        select(MetaSpells).where(col(MetaSpells.patch).in_(patches), MetaSpells.champion_key == champ.key, MetaSpells.role == role)
    ).all():
        pairs[r.spells][0] += r.games
        pairs[r.spells][1] += r.wins
    if not pairs:
        return None
    total = sum(g for g, _ in pairs.values())
    key, (games, wins) = max(pairs.items(), key=lambda kv: (kv[1][0], kv[1][1]))
    ids = sorted((int(x) for x in key.split(",")), key=lambda i: (i == FLASH, i))
    names = (static or {}).get("spells", {})
    return {
        "spells": [{"id": i, **names.get(i, {"name": f"Spell {i}", "icon": None})} for i in ids],
        "games": games,
        "pick_rate": games / total if total else None,
        "win_rate": _rate(wins, games),
    }


def suggest_bans(
    session: Session, champs: list[Champion], patches: list[str], n: int = BAN_COUNT, exclude: set[str] | None = None
) -> list[dict]:
    """Enemy champions the rolled champions do worst against, in high elo.

    For each rolled champion, its win rate against an enemy is pulled toward its overall win rate by
    BAN_PRIOR_GAMES games, so a 0-2 record doesn't outrank a 40-60 one. An enemy's threat is how far it
    drags those win rates down, added up over the rolled champions. Our own champions, and any in
    `exclude` (everyone's backup options), are never bans.
    """
    if not patches or not champs:
        return []
    ours = {c.key: c for c in champs}
    base: dict[int, float] = {}
    for key in ours:
        games = wins = 0
        for r in session.exec(
            select(MetaChampRole).where(MetaChampRole.champion_key == key, col(MetaChampRole.patch).in_(patches))
        ).all():
            games += r.games
            wins += r.wins
        base[key] = wins / games if games else 0.5

    vs: dict[int, dict[int, list[int]]] = defaultdict(lambda: defaultdict(lambda: [0, 0]))  # enemy -> ours -> [g, w]
    for r in session.exec(
        select(MetaMatchup).where(col(MetaMatchup.champion_key).in_(list(ours)), col(MetaMatchup.patch).in_(patches))
    ).all():
        if r.enemy_key not in ours:
            vs[r.enemy_key][r.champion_key][0] += r.games
            vs[r.enemy_key][r.champion_key][1] += r.wins

    by_key = {c.key: c.id for c in session.exec(select(Champion)).all()}
    scored = []
    for enemy, rows in vs.items():
        if enemy not in by_key or by_key[enemy] in (exclude or ()):
            continue
        threat, games, wins, against = 0.0, 0, 0, []
        for key, (g, w) in rows.items():
            shrunk = (w + BAN_PRIOR_GAMES * base[key]) / (g + BAN_PRIOR_GAMES)
            threat += base[key] - shrunk
            games, wins = games + g, wins + w
            against.append({"champion_id": ours[key].id, "games": g, "win_rate": _rate(w, g)})
        if threat > 0:
            scored.append(
                {
                    "champion_id": by_key[enemy],
                    "threat": round(threat, 4),
                    "games": games,
                    "win_rate": _rate(wins, games),  # our rolled champions' combined record against it
                    "against": sorted(against, key=lambda a: -a["games"]),
                }
            )
    scored.sort(key=lambda b: -b["threat"])
    return scored[:n]


def describe_page(page: str, games: int, wins: int, static: dict | None) -> dict:
    primary, sub, shards = page.split("|")
    p_style, p_perks = primary.split(":")
    s_style, s_perks = sub.split(":")
    names = (static or {}).get("perks", {})

    def perk(pid: str) -> dict:
        i = int(pid)
        return {"id": i, **names.get(i, {"name": SHARD_NAMES.get(i, f"Rune {i}"), "icon": None})}

    perks = [perk(x) for x in p_perks.split(",") if x]
    return {
        "primary": perk(p_style),
        "keystone": perks[0] if perks else None,
        "primary_perks": perks[1:],
        "secondary": perk(s_style),
        "secondary_perks": [perk(x) for x in s_perks.split(",") if x],
        "shards": [{"id": int(x), "name": SHARD_NAMES.get(int(x), f"Shard {x}")} for x in shards.split(",") if x and x != "0"],
        "games": games,
        "win_rate": _rate(wins, games),
    }


def suggest_comp(
    session: Session, champion_ids: list[str], static: dict | None = None, exclude: list[str] | None = None
) -> dict:
    champs = {c.id: c for c in session.exec(select(Champion).where(col(Champion.id).in_(champion_ids))).all()}
    order = [cid for cid in champion_ids if cid in champs][: len(ROLES)]
    patches = recent_patches(session)
    scored = [role_scores(session, champs[cid], patches) for cid in order]
    roles = best_assignment([s for s, _, _ in scored])
    picks = []
    for cid, role, (_, source, rows) in zip(order, roles, scored, strict=False):
        champ = champs[cid]
        total = sum(r.games for r in rows.values())
        row = rows.get(role)
        off_role = source == "high-elo" and (row.games if row else 0) < OFF_ROLE_SHARE * total
        # Off-role: show the build from the role the champ is usually played in.
        build_role = max(rows.values(), key=lambda r: r.games).role if off_role else role
        runes, items, boots = build_for(session, champ, build_role, patches, static)
        spells = spells_for(session, champ, build_role, patches, static)
        picks.append(
            Pick(
                champion_id=cid,
                role=role,
                role_name=ROLE_NAMES[role],
                role_source=source,
                role_games=row.games if row else 0,
                role_win_rate=_rate(row.wins, row.games) if row else None,
                off_role=off_role,
                build_role=build_role,
                runes=runes,
                items=items,
                boots=boots,
                spells=spells,
            )
        )
    matches = session.exec(select(func.count()).select_from(MetaMatch)).one()
    bans = suggest_bans(session, [champs[cid] for cid in order], patches, exclude=set(exclude or []))
    return {"patches": patches, "matches": matches, "picks": picks, "bans": bans}


# --- champion positions from Meraki Analytics (community data, no key needed) ----------------

MERAKI_URL = "https://cdn.merakianalytics.com/riot/lol/resources/latest/en-US/champions.json"


def parse_positions(data: dict) -> dict[str, list[str]]:
    return {cid: list(c.get("positions") or []) for cid, c in data.items()}


async def refresh_positions(session: Session, client: httpx.AsyncClient | None = None) -> int:
    own = client is None
    client = client or httpx.AsyncClient(timeout=60)
    try:
        data = (await client.get(MERAKI_URL)).raise_for_status().json()
    finally:
        if own:
            await client.aclose()
    positions = parse_positions(data)
    count = 0
    for champ in session.exec(select(Champion)).all():
        if champ.id in positions:
            champ.positions = positions[champ.id]
            session.add(champ)
            count += 1
    session.flush()
    return count
