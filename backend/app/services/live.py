"""Live game tracking: find the League game a pending challenge game is being played in, fill in
everyone's champion, and keep a broadcast-style summary of the game while it runs.

Two sources, both optional:

- **Spectator-V5** (Riot API, needs a key): once the game has loaded, gives each player's champion,
  summoner spells, runes and the bans. No gold, items or scores.
- **Live Client Data API** (the game client, https://127.0.0.1:2999, only on a PC that is in the
  game): every player's items, level, KDA, CS and wards, plus the kill and objective events. Gold is
  only given for the local player, so team and lane gold are estimated from item value, the way
  broadcasts without official data do it.

Summoner spells are shown but cooldowns are never tracked (Riot's game-integrity rules).
"""

from dataclasses import dataclass
from datetime import UTC, datetime

import httpx
from sqlmodel import Session, col, select

from app.config import get_settings
from app.models import ChallengeGame, Champion, LiveGame, Player, Run, utcnow
from app.services import rules

BLUE, RED = 100, 200
TEAM_OF = {"ORDER": BLUE, "CHAOS": RED}
EVENT_LIMIT = 40  # newest events kept in the summary
GOLD_SAMPLE_SECONDS = 30  # gold lead graph: one point per 30 game seconds
OBJECTIVES = {
    "DragonKill": "dragon",
    "BaronKill": "baron",
    "HeraldKill": "herald",
    "HordeKill": "grubs",
    "AtakhanKill": "atakhan",
}


# --- which game is ours ------------------------------------------------------------------


def pending_game(session: Session) -> ChallengeGame | None:
    """The newest pending challenge game in an active run."""
    active = select(Run.id).where(Run.status == "active")
    return session.exec(
        select(ChallengeGame)
        .where(ChallengeGame.status == "pending", col(ChallengeGame.run_id).in_(active))
        .order_by(col(ChallengeGame.id).desc())
    ).first()


def tracked_players(session: Session, game: ChallengeGame) -> dict[int, Player]:
    ids = [a.player_id for a in rules.assignments_for(session, game.id)]
    return {p.id: p for p in session.exec(select(Player).where(col(Player.id).in_(ids))).all()}


def _riot_id(name: str | None, tag: str | None) -> str | None:
    return f"{name}#{tag}".lower() if name and tag else None


def _champ_by_key(session: Session) -> dict[int, Champion]:
    return {c.key: c for c in session.exec(select(Champion)).all()}


def autofill_picks(session: Session, game: ChallengeGame, champions: dict[int, str]) -> list[str]:
    """Set each player's played champion from the live game (player_id -> champion id).

    Only fills players nobody has marked yet; a pick someone set by hand is left alone and any
    difference is returned as a note.
    """
    notes, picks = [], []
    taken = {a.played_champion_id for a in rules.assignments_for(session, game.id) if a.played_champion_id}
    names = {p.id: p.display_name for p in session.exec(select(Player)).all()}
    for a in rules.assignments_for(session, game.id):
        cid = champions.get(a.player_id)
        if not cid:
            continue
        if a.played_champion_id is None and cid not in taken:
            picks.append(rules.Pick(player_id=a.player_id, champion_id=cid))
        elif a.played_champion_id and a.played_champion_id != cid:
            notes.append(f"{names.get(a.player_id, a.player_id)} is on {cid} in the live game, but {a.played_champion_id} is marked")
    if picks:
        rules.set_played(session, game, picks)
    return notes


def _live_row(session: Session, game: ChallengeGame) -> LiveGame:
    row = session.get(LiveGame, game.id)
    if row is None:
        row = LiveGame(game_id=game.id)
        session.add(row)
    return row


# --- Spectator-V5 -------------------------------------------------------------------------


def apply_spectator(session: Session, game: ChallengeGame, data: dict) -> LiveGame | None:
    """Record a Spectator-V5 game if every linked player of `game` is in it, on one team."""
    players = tracked_players(session, game)
    by_puuid = {p.puuid: p.id for p in players.values() if p.puuid}
    parts = data.get("participants", [])
    ours = {by_puuid[p["puuid"]]: p for p in parts if p.get("puuid") in by_puuid}
    if not ours or len(ours) < len(by_puuid) or len({p.get("teamId") for p in ours.values()}) > 1:
        return None
    champs = _champ_by_key(session)
    row = _live_row(session, game)
    row.riot_game_id = data.get("gameId")
    row.platform = data.get("platformId")
    row.queue_id = data.get("gameQueueConfigId")
    start = data.get("gameStartTime") or 0
    row.started_at = datetime.fromtimestamp(start / 1000, UTC) if start > 0 else row.started_at
    row.checked_at = utcnow()
    row.our_team = next(iter(ours.values())).get("teamId")
    row.participants = [
        {
            "champion_id": champs[p["championId"]].id if p.get("championId") in champs else None,
            "team": p.get("teamId"),
            "spells": [p.get("spell1Id"), p.get("spell2Id")],
            "keystone": ((p.get("perks") or {}).get("perkIds") or [None])[0],
            "player_id": by_puuid.get(p.get("puuid")),
        }
        for p in parts
    ]
    row.bans = [
        {"champion_id": champs[b["championId"]].id, "team": b.get("teamId")}
        for b in data.get("bannedChampions", [])
        if b.get("championId") in champs
    ]
    session.add(row)
    notes = autofill_picks(
        session, game, {pid: champs[p["championId"]].id for pid, p in ours.items() if p.get("championId") in champs}
    )
    if notes:
        row.state = {**row.state, "notes": notes}
    return row


async def check_spectator(session: Session, client, game: ChallengeGame) -> LiveGame | None:
    """Ask Riot whether the game's players are in a game now. Commits; never holds the database
    while waiting on Riot. Marks an already-found game as ended once Riot stops listing it."""
    players = [p for p in tracked_players(session, game).values() if p.puuid]
    row = session.get(LiveGame, game.id)
    session.commit()
    if not players:
        return row
    data = await client.active_game(players[0].platform, players[0].puuid)
    game = session.get(ChallengeGame, game.id)
    row = session.get(LiveGame, game.id)
    if data is None:
        if row is not None and row.riot_game_id and row.ended_at is None:
            row.ended_at = utcnow()
            session.add(row)
        elif row is not None:
            row.checked_at = utcnow()
            session.add(row)
        session.commit()
        return row
    if row is not None and row.riot_game_id and data.get("gameId") != row.riot_game_id:
        session.commit()
        return row  # a different game than the one we found (keep the first)
    found = apply_spectator(session, game, data)
    session.commit()
    return found or row


# --- Live Client Data API ------------------------------------------------------------------


async def fetch_live_client(http: httpx.AsyncClient | None = None) -> dict | None:
    """allgamedata from the game client on this PC, or None when no game is running here."""
    base = get_settings().live_client_url
    if not base or base.strip().lower() in ("off", "none", "disabled"):
        return None
    own = http is None
    # The game client serves a self-signed certificate on localhost.
    http = http or httpx.AsyncClient(verify=False, timeout=2)
    try:
        res = await http.get(f"{base.rstrip('/')}/liveclientdata/allgamedata")
        if res.status_code != 200:
            return None  # still loading (404) or not ready
        data = res.json()
        return data if isinstance(data, dict) and data.get("allPlayers") else None
    except (httpx.HTTPError, ValueError):
        return None
    finally:
        if own:
            await http.aclose()


def _client_riot_id(p: dict) -> str | None:
    name, tag = p.get("riotIdGameName"), p.get("riotIdTagLine")
    if name and tag:
        return f"{name}#{tag}".lower()
    rid = p.get("riotId") or ""
    return rid.lower() if "#" in rid else None


def _client_champion(p: dict, champs_by_id: dict[str, Champion], champs_by_name: dict[str, Champion]) -> str | None:
    raw = p.get("rawChampionName") or ""
    if raw.startswith("game_character_displayname_"):
        cid = raw.removeprefix("game_character_displayname_")
        if cid in champs_by_id:
            return cid
    c = champs_by_name.get((p.get("championName") or "").lower())
    return c.id if c else None


def match_client_game(session: Session, game: ChallengeGame, data: dict) -> dict[int, dict] | None:
    """player_id -> Live Client player, if every player with a Riot ID is in this game on one team."""
    players = tracked_players(session, game)
    wanted = {_riot_id(p.riot_game_name, p.riot_tag_line): pid for pid, p in players.items()}
    wanted.pop(None, None)
    found = {}
    for p in data.get("allPlayers", []):
        pid = wanted.get(_client_riot_id(p))
        if pid is not None:
            found[pid] = p
    if not wanted or len(found) < len(wanted) or len({p.get("team") for p in found.values()}) > 1:
        return None
    return found


@dataclass
class Static:
    """Names and icons from Data Dragon (meta.load_static); everything works without it."""

    items: dict
    perks: dict
    spells_by_name: dict  # "SummonerFlash" -> {"name", "icon"}

    @classmethod
    def from_meta(cls, static: dict | None) -> "Static":
        static = static or {}
        return cls(static.get("items", {}), static.get("perks", {}), static.get("spells_by_name", {}))


def _spell(s: dict | None, static: Static) -> dict | None:
    if not s:
        return None
    raw = s.get("rawDisplayName") or ""  # "GeneratedTip_SummonerSpell_SummonerFlash_DisplayName"
    key = raw.split("_")[2] if raw.count("_") >= 3 else None
    info = static.spells_by_name.get(key or "", {})
    return {"name": info.get("name") or s.get("displayName") or key, "icon": info.get("icon")}


def _turret_team(name: str) -> int | None:
    """Which team lost a turret or inhibitor, from names like "Turret_T1_C_05_A" (T1 = blue's)."""
    if "_T1_" in name:
        return BLUE
    if "_T2_" in name:
        return RED
    return None


def summarize(session: Session, game: ChallengeGame, data: dict, previous: dict | None, static: dict | None = None) -> dict:
    """The broadcast summary stored on LiveGame.state (the raw client data is not kept)."""
    st = Static.from_meta(static)
    champs = session.exec(select(Champion)).all()
    by_id = {c.id: c for c in champs}
    by_name = {c.name.lower(): c for c in champs}
    ours = match_client_game(session, game, data) or {}
    pid_by_rid = {_client_riot_id(p): pid for pid, p in ours.items()}
    options = {a.player_id: a for a in rules.assignments_for(session, game.id)}
    game_time = float((data.get("gameData") or {}).get("gameTime") or 0)

    # In-game names are only used to tie events to players; they're never stored. Opponents are
    # labelled by champion, our players by their app name (services/privacy.py).
    players, name_team, name_who = [], {}, {}
    for p in data.get("allPlayers", []):
        team = TEAM_OF.get(p.get("team"), BLUE)
        cid = _client_champion(p, by_id, by_name)
        items, item_gold = [], 0
        for it in sorted(p.get("items", []), key=lambda i: i.get("slot", 0)):
            iid = it.get("itemID")
            info = st.items.get(iid, {})
            count = it.get("count") or 1
            item_gold += (info.get("total") or it.get("price") or 0) * count
            items.append(
                {"id": iid, "name": info.get("name") or it.get("displayName"), "image": info.get("image"), "count": count, "slot": it.get("slot")}
            )
        scores = p.get("scores") or {}
        keystone = ((p.get("runes") or {}).get("keystone") or {})
        pid = pid_by_rid.get(_client_riot_id(p))
        a = options.get(pid) if pid else None
        rid = p.get("riotIdGameName") or (p.get("riotId") or "").split("#")[0] or p.get("summonerName") or ""
        for n in {rid, p.get("summonerName"), p.get("riotId")}:
            if n:
                name_team[n] = team
                name_who[n] = {"champion_id": cid, "player_id": pid}
        players.append(
            {
                "champion_id": cid,
                "team": team,
                "position": p.get("position") or "",
                "level": p.get("level", 1),
                "kills": scores.get("kills", 0),
                "deaths": scores.get("deaths", 0),
                "assists": scores.get("assists", 0),
                "cs": scores.get("creepScore", 0),
                "wards": round(scores.get("wardScore", 0), 1),
                "items": items,
                "item_gold": item_gold,
                "spells": [
                    _spell((p.get("summonerSpells") or {}).get("summonerSpellOne"), st),
                    _spell((p.get("summonerSpells") or {}).get("summonerSpellTwo"), st),
                ],
                "keystone": {
                    "id": keystone.get("id"),
                    "name": keystone.get("displayName"),
                    "icon": st.perks.get(keystone.get("id"), {}).get("icon"),
                }
                if keystone
                else None,
                "dead": bool(p.get("isDead")),
                "respawn": round(p.get("respawnTimer") or 0) if p.get("isDead") else 0,
                "player_id": pid,
                "option_index": (a.options.index(cid) if a and cid in a.options else None) if a else None,
            }
        )

    teams = {str(t): {"kills": 0, "gold": 0, "towers": 0, "inhibitors": 0, "dragons": [], "barons": 0, "heralds": 0, "grubs": 0, "atakhan": 0} for t in (BLUE, RED)}
    for p in players:
        teams[str(p["team"])]["kills"] += p["kills"]
        teams[str(p["team"])]["gold"] += p["item_gold"]

    events, result = [], None

    def who(name: str | None) -> dict | None:
        """A champion (and our player, if it's one of ours) in place of an in-game name."""
        return name_who.get(name) if name else None

    other = {BLUE: RED, RED: BLUE}
    for e in (data.get("events") or {}).get("Events", []):
        name, t = e.get("EventName"), round(e.get("EventTime", 0))
        if name == "ChampionKill":
            team = name_team.get(e.get("KillerName"))
            events.append({"t": t, "type": "kill", "killer": who(e.get("KillerName")), "victim": who(e.get("VictimName")), "team": team or other.get(name_team.get(e.get("VictimName")))})
        elif name == "Multikill":
            events.append({"t": t, "type": "multikill", "killer": who(e.get("KillerName")), "streak": e.get("KillStreak"), "team": name_team.get(e.get("KillerName"))})
        elif name == "FirstBlood":
            events.append({"t": t, "type": "first_blood", "killer": who(e.get("Recipient")), "team": name_team.get(e.get("Recipient"))})
        elif name == "Ace":
            events.append({"t": t, "type": "ace", "team": TEAM_OF.get(e.get("AcingTeam"))})
        elif name in OBJECTIVES:
            team = name_team.get(e.get("KillerName"))
            kind = OBJECTIVES[name]
            if team:
                bucket = teams[str(team)]
                if kind == "dragon":
                    bucket["dragons"].append(e.get("DragonType") or "Dragon")
                else:
                    bucket[{"baron": "barons", "herald": "heralds"}.get(kind, kind)] += 1
            events.append({"t": t, "type": kind, "detail": e.get("DragonType"), "stolen": e.get("Stolen") == "True", "killer": who(e.get("KillerName")), "team": team})
        elif name in ("TurretKilled", "InhibKilled"):
            lost = _turret_team(e.get("TurretKilled") or e.get("InhibKilled") or "")
            if lost:
                teams[str(other[lost])]["towers" if name == "TurretKilled" else "inhibitors"] += 1
            events.append({"t": t, "type": "tower" if name == "TurretKilled" else "inhibitor", "team": other.get(lost)})
        elif name == "GameEnd":
            result = e.get("Result")

    # Gold lead over time (blue minus red), one point per GOLD_SAMPLE_SECONDS of game time.
    history = list((previous or {}).get("gold_history", []))
    diff = teams[str(BLUE)]["gold"] - teams[str(RED)]["gold"]
    if not history or game_time - history[-1]["t"] >= GOLD_SAMPLE_SECONDS:
        history.append({"t": round(game_time), "diff": diff})
    elif game_time < history[-1]["t"]:
        history = [{"t": round(game_time), "diff": diff}]  # a different game: start over

    our_team = next((p["team"] for p in players if p["player_id"]), None)
    return {
        "game_time": round(game_time),
        "game_mode": (data.get("gameData") or {}).get("gameMode"),
        "our_team": our_team,
        "teams": teams,
        "players": players,
        "events": events[-EVENT_LIMIT:][::-1],
        "gold_history": history[-240:],
        "result": result,  # "Win" / "Lose" for this PC's player, once the game ends
        "notes": (previous or {}).get("notes", []),
    }


def apply_client(session: Session, game: ChallengeGame, data: dict, static: dict | None = None) -> LiveGame | None:
    """Store the Live Client summary for `game` (and fill in picks) if our players are in it."""
    ours = match_client_game(session, game, data)
    if not ours:
        return None
    row = _live_row(session, game)
    state = summarize(session, game, data, row.state, static)
    champs = {p["player_id"]: p["champion_id"] for p in state["players"] if p["player_id"] and p["champion_id"]}
    notes = autofill_picks(session, game, champs)
    state["notes"] = sorted(set(state["notes"]) | set(notes))
    row.state = state
    row.our_team = row.our_team or state["our_team"]
    row.updated_at = utcnow()
    if state["result"] and row.ended_at is None:
        row.ended_at = utcnow()
    session.add(row)
    return row


def live_out(session: Session, row: LiveGame | None, static: dict | None = None) -> dict | None:
    """What the Live tab and the overlay read."""
    if row is None:
        return None
    spells = (static or {}).get("spells", {})
    perks = (static or {}).get("perks", {})
    participants = [
        {
            **p,
            "spells": [{"id": s, **spells.get(s, {"name": f"Spell {s}", "icon": None})} for s in p.get("spells", []) if s],
            "keystone": {"id": p.get("keystone"), **perks.get(p.get("keystone"), {})} if p.get("keystone") else None,
        }
        for p in row.participants
    ]
    stale = row.updated_at is None or (utcnow() - row.updated_at).total_seconds() > 20
    return {
        "game_id": row.game_id,
        "riot_game_id": row.riot_game_id,
        "platform": row.platform,
        "queue_id": row.queue_id,
        "started_at": row.started_at,
        "detected_at": row.detected_at,
        "updated_at": row.updated_at,
        "ended_at": row.ended_at,
        "our_team": row.our_team,
        "participants": participants,
        "bans": row.bans,
        "state": row.state or None,
        # Live stats are flowing right now (not just "found through Spectator").
        "streaming": not stale and row.ended_at is None,
    }

