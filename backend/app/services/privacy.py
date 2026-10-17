"""Keeping as little Riot data about people as the app needs, and deleting it on request.

Riot's API terms make apps responsible for the Game Information they hold: honour deletion requests
(Riot forwards GDPR "forget me" lists of player IDs to developers) and delete everything if API
access ends. So:

- Stored matches keep each participant's game numbers (needed for grades and team stats) but only
  the identity (PUUID) of players registered in the app. Names, PUUIDs, summoner ids and icons of
  everyone else are removed before saving (`scrub_match`).
- Live games label opponents by champion, never by name (services/live.py).
- The high-elo crawler keeps only win/loss totals per champion; its queue of ladder PUUIDs is
  temporary and replaced every 12 hours.
- `forget_player` / `forget_puuids` / `purge_all` delete on request (Settings, or
  `python -m app.privacy_cli`).
"""

from sqlmodel import Session, col, delete, select

from app.models import (
    LiveGame,
    MetaChampRole,
    MetaCrawlState,
    MetaItem,
    MetaMatch,
    MetaMatchup,
    MetaRunePage,
    MetaSpells,
    Player,
    PlayerMatchStats,
    RiotMatch,
)

# Match-V5 participant fields that identify a person (everything else is game numbers).
IDENTITY_FIELDS = (
    "puuid",
    "riotIdGameName",
    "riotIdName",
    "riotIdTagline",
    "summonerName",
    "summonerId",
    "summonerLevel",
    "profileIcon",
)


def registered_puuids(session: Session) -> set[str]:
    return {p for p in session.exec(select(Player.puuid).where(col(Player.puuid).is_not(None))).all() if p}


def scrub_match(raw: dict, keep: set[str]) -> dict:
    """A copy of a Match-V5 response with nobody identifiable except the players in `keep`
    (who keep only their PUUID, which is how the app recognises them)."""
    info = dict(raw.get("info") or {})
    participants = []
    for p in info.get("participants", []):
        p = dict(p)
        mine = p.get("puuid") in keep
        for f in IDENTITY_FIELDS:
            if not (mine and f == "puuid"):
                p.pop(f, None)
        participants.append(p)
    info["participants"] = participants
    info.pop("gameName", None)
    meta = {"matchId": (raw.get("metadata") or {}).get("matchId")}
    return {"metadata": meta, "info": info}


def scrub_stored_matches(session: Session) -> int:
    """Scrub every stored match (for data saved before scrubbing existed). Returns how many changed."""
    keep = registered_puuids(session)
    changed = 0
    for m in session.exec(select(RiotMatch)).all():
        clean = scrub_match(m.raw_json or {}, keep)
        if clean != m.raw_json:
            m.raw_json = clean
            session.add(m)
            changed += 1
    return changed


def _drop_puuid_from_matches(session: Session, puuids: set[str]) -> None:
    for m in session.exec(select(RiotMatch)).all():
        parts = (m.raw_json or {}).get("info", {}).get("participants", [])
        if any(p.get("puuid") in puuids for p in parts):
            m.raw_json = scrub_match(m.raw_json, registered_puuids(session) - puuids)
            session.add(m)


def _drop_orphan_matches(session: Session) -> None:
    """Matches no registered player's stats point at any more."""
    used = set(session.exec(select(PlayerMatchStats.match_id).distinct()).all())
    for m in session.exec(select(RiotMatch)).all():
        if m.match_id not in used:
            session.delete(m)


def forget_player(session: Session, player: Player) -> None:
    """Delete everything from Riot about one player: their PUUID, Riot ID and match stats.

    The challenge itself stays (who played which champion, wins and losses, gold and items are
    the app's own records), but KDA, grades and other match stats for this player are gone.
    """
    puuid = player.puuid
    session.exec(delete(PlayerMatchStats).where(col(PlayerMatchStats.player_id) == player.id))
    player.puuid = None
    player.riot_game_name = None
    player.riot_tag_line = None
    session.add(player)
    session.flush()
    if puuid:
        _drop_puuid_from_matches(session, {puuid})
        _forget_in_crawler(session, {puuid})
    _drop_orphan_matches(session)
    session.flush()


def _forget_in_crawler(session: Session, puuids: set[str]) -> None:
    state = session.get(MetaCrawlState, 1)
    if state and any(p in puuids for p in state.puuids):
        before = state.puuids[: state.next_index]
        removed_before = sum(p in puuids for p in before)
        state.puuids = [p for p in state.puuids if p not in puuids]
        state.next_index = max(0, state.next_index - removed_before)
        session.add(state)


def forget_puuids(session: Session, puuids: list[str]) -> dict:
    """Handle a deletion list from Riot: forget any of these players, wherever they appear."""
    wanted = {p.strip() for p in puuids if p and p.strip()}
    players = session.exec(select(Player).where(col(Player.puuid).in_(list(wanted)))).all()
    for player in players:
        forget_player(session, player)
    _drop_puuid_from_matches(session, wanted)
    _forget_in_crawler(session, wanted)
    session.flush()
    return {"requested": len(wanted), "players_forgotten": len(players)}


def purge_all(session: Session) -> dict:
    """Delete all Game Information (what the API terms require if API access ends).

    Keeps the app's own records: players' names, runs, the pool, spins, results, gold and items.
    """
    counts = {
        "match_stats": len(session.exec(select(PlayerMatchStats.match_id)).all()),
        "matches": len(session.exec(select(RiotMatch.match_id)).all()),
    }
    for model in (PlayerMatchStats, RiotMatch, LiveGame, MetaMatch, MetaChampRole, MetaRunePage, MetaItem, MetaSpells, MetaMatchup):
        session.exec(delete(model))
    state = session.get(MetaCrawlState, 1)
    if state:
        state.puuids, state.next_index, state.matches_counted, state.refreshed_at = [], 0, 0, None
        session.add(state)
    for p in session.exec(select(Player).where(col(Player.puuid).is_not(None))).all():
        p.puuid = None
        session.add(p)
    session.flush()
    return counts
