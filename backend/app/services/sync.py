"""Linking Riot IDs and importing matches into RiotMatch / PlayerMatchStats (SPEC 9.1, 9.3)."""

from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlmodel import Session, col, select

from app.models import AppSettings, Player, PlayerMatchStats, RiotMatch, utcnow
from app.services.riot_client import RiotClient, RiotError

RECENT_MATCH_COUNT = 20


async def link_player(session: Session, client: RiotClient, player: Player) -> Player:
    """Resolve the player's PUUID from their Riot ID. Raises RiotError (404 if the Riot ID doesn't exist)."""
    if not player.riot_game_name or not player.riot_tag_line:
        raise RiotError(400, "Enter a Riot ID (Name#TAG) first")
    account = await client.account_by_riot_id(player.region, player.riot_game_name, player.riot_tag_line)
    player.puuid = account["puuid"]
    # Use Riot's capitalisation
    player.riot_game_name = account.get("gameName") or player.riot_game_name
    player.riot_tag_line = account.get("tagLine") or player.riot_tag_line
    session.add(player)
    session.flush()
    return player


# --- parsing ------------------------------------------------------------------


def parse_match(raw: dict) -> RiotMatch:
    info = raw["info"]
    start_ms = info.get("gameStartTimestamp") or info.get("gameCreation")
    duration = info.get("gameDuration", 0)
    if "gameEndTimestamp" not in info:  # matches before patch 11.20 report milliseconds
        duration //= 1000
    return RiotMatch(
        match_id=raw["metadata"]["matchId"],
        queue_id=info.get("queueId", 0),
        game_start=datetime.fromtimestamp(start_ms / 1000, UTC) if start_ms else None,
        game_duration=duration,
        early_surrender=any(p.get("gameEndedInEarlySurrender") for p in info.get("participants", [])),
        raw_json=raw,
    )


def team_kills(raw: dict) -> dict[int, int]:
    kills: dict[int, int] = {}
    for p in raw["info"]["participants"]:
        kills[p["teamId"]] = kills.get(p["teamId"], 0) + p.get("kills", 0)
    return kills


def participant_stats(match: RiotMatch, player_id: int, p: dict, kills_by_team: dict[int, int]) -> PlayerMatchStats:
    return PlayerMatchStats(
        match_id=match.match_id,
        player_id=player_id,
        champion_key=p["championId"],
        team_id=p["teamId"],
        win=bool(p.get("win")),
        kills=p.get("kills", 0),
        deaths=p.get("deaths", 0),
        assists=p.get("assists", 0),
        team_kills=kills_by_team.get(p["teamId"], 0),
        cs=p.get("totalMinionsKilled", 0) + p.get("neutralMinionsKilled", 0),
        gold=p.get("goldEarned", 0),
        damage_to_champs=p.get("totalDamageDealtToChampions", 0),
        vision_score=p.get("visionScore", 0),
        game_duration=match.game_duration,
        queue_id=match.queue_id,
    )


def store_match(session: Session, raw: dict) -> RiotMatch:
    """Save a match and a PlayerMatchStats row for every registered player who was in it."""
    match = parse_match(raw)
    session.merge(match)
    by_puuid = {
        p.puuid: p.id for p in session.exec(select(Player).where(col(Player.puuid).is_not(None))).all()
    }
    kills_by_team = team_kills(raw)
    for p in raw["info"]["participants"]:
        player_id = by_puuid.get(p.get("puuid"))
        if player_id is None or session.get(PlayerMatchStats, (match.match_id, player_id)):
            continue
        session.add(participant_stats(match, player_id, p, kills_by_team))
    session.flush()
    return match


# --- syncing --------------------------------------------------------------------


@dataclass
class SyncResult:
    players_synced: int = 0
    new_matches: int = 0
    errors: list[str] = field(default_factory=list)


async def import_player_matches(
    session: Session, client: RiotClient, player: Player, count: int = RECENT_MATCH_COUNT
) -> int:
    """Fetch the player's recent match IDs and store any matches we don't have yet."""
    ids = await client.match_ids(player.region, player.puuid, count=count)
    new = 0
    for match_id in ids:
        if session.get(RiotMatch, match_id):
            # Already cached; make sure this player's row exists (they may have been linked later).
            if not session.get(PlayerMatchStats, (match_id, player.id)):
                store_match(session, session.get(RiotMatch, match_id).raw_json)
            continue
        store_match(session, await client.match(player.region, match_id))
        new += 1
    return new


async def sync_all(session: Session, client: RiotClient) -> SyncResult:
    result = SyncResult()
    players = session.exec(select(Player).where(col(Player.puuid).is_not(None))).all()
    for player in players:
        try:
            result.new_matches += await import_player_matches(session, client, player)
            result.players_synced += 1
            session.commit()
        except RiotError as e:
            session.rollback()
            result.errors.append(f"{player.display_name}: {e}")
            if e.status in (0, 401, 403):  # key problem: every other call will fail too
                break

    settings = session.get(AppSettings, 1) or AppSettings(id=1)
    settings.last_sync_at = utcnow()
    settings.last_sync_error = "; ".join(result.errors) or None
    session.add(settings)
    session.commit()
    return result
