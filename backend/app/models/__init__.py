"""SQLModel tables. See SPEC.md section 8."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, Column, DateTime, TypeDecorator
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(UTC)


class UTCDateTime(TypeDecorator):
    """Stores datetimes as UTC and always returns timezone-aware values (SQLite drops tzinfo)."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect):
        if value is not None and value.tzinfo is not None:
            value = value.astimezone(UTC).replace(tzinfo=None)
        return value

    def process_result_value(self, value: datetime | None, dialect):
        if value is not None and value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value


def dt_field(*, nullable: bool = True, default_now: bool = False) -> Any:
    if default_now:
        return Field(default_factory=utcnow, sa_type=UTCDateTime, nullable=False)
    return Field(default=None, sa_type=UTCDateTime, nullable=nullable)


def json_field(default_factory=list) -> Any:
    return Field(default_factory=default_factory, sa_column=Column(JSON, nullable=False))


# ---------------------------------------------------------------------------


class Player(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    display_name: str
    riot_game_name: str | None = None
    riot_tag_line: str | None = None
    puuid: str | None = Field(default=None, index=True)
    platform: str = "na1"
    region: str = "americas"
    created_at: datetime = dt_field(default_now=True)


class Champion(SQLModel, table=True):
    id: str = Field(primary_key=True)  # Data Dragon id, e.g. "MonkeyKing"
    key: int = Field(unique=True, index=True)  # numeric key used in match data
    name: str
    title: str = ""
    tags: list[str] = json_field()
    image_url: str = ""
    ddragon_version: str = ""


class Run(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str
    status: str = "active"  # "active" | "ended"
    options_per_player: int = 3  # 3 | 4
    win_count: int = 0
    current_streak: int = 0
    best_streak: int = 0
    started_at: datetime = dt_field(default_now=True)
    ended_at: datetime | None = dt_field()


class PoolEntry(SQLModel, table=True):
    run_id: int = Field(foreign_key="run.id", primary_key=True)
    champion_id: str = Field(foreign_key="champion.id", primary_key=True)
    status: str = "alive"  # "alive" | "eliminated"
    eliminated_at: datetime | None = dt_field()
    eliminated_in_game_id: int | None = Field(default=None, foreign_key="challengegame.id")
    eliminated_by_player_id: int | None = Field(default=None, foreign_key="player.id")


class ChallengeGame(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    run_id: int = Field(foreign_key="run.id", index=True)
    created_at: datetime = dt_field(default_now=True)
    status: str = "pending"  # "pending" | "won" | "lost" | "void"
    result_source: str | None = None  # "auto" | "manual"
    riot_match_id: str | None = None
    resolved_at: datetime | None = dt_field()
    void_reason: str | None = None
    # Auto-matching: a candidate match failed a check and is waiting for the user (riot_match_id holds it).
    needs_review: bool = False
    review_reason: str | None = None
    # Matches the user rejected (or undid), so the matcher won't pick them again.
    rejected_match_ids: list[str] = json_field()
    # Run counters captured just before the result was applied, so undo can restore them exactly.
    prev_win_count: int | None = None
    prev_current_streak: int | None = None
    prev_best_streak: int | None = None


class SpinAssignment(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    game_id: int = Field(foreign_key="challengegame.id", index=True)
    player_id: int = Field(foreign_key="player.id")
    options: list[str] = json_field()  # ordered champion ids
    played_champion_id: str | None = Field(default=None, foreign_key="champion.id")
    played_option_index: int | None = None  # 0-based; None with a champion set means "other"


class ReviveToken(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    run_id: int = Field(foreign_key="run.id", index=True)
    player_id: int = Field(foreign_key="player.id")
    earned_in_game_id: int = Field(foreign_key="challengegame.id")
    used_at: datetime | None = dt_field()
    revived_champion_id: str | None = Field(default=None, foreign_key="champion.id")


class PoolEvent(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    run_id: int = Field(foreign_key="run.id", index=True)
    game_id: int | None = Field(default=None, foreign_key="challengegame.id")
    # "eliminate" | "revive" | "manual_eliminate" | "manual_revive"
    type: str
    champion_id: str | None = Field(default=None, foreign_key="champion.id")
    player_id: int | None = Field(default=None, foreign_key="player.id")
    token_id: int | None = Field(default=None, foreign_key="revivetoken.id")
    created_at: datetime = dt_field(default_now=True)
    undone: bool = False


class RiotMatch(SQLModel, table=True):
    match_id: str = Field(primary_key=True)
    queue_id: int
    game_start: datetime | None = dt_field()
    game_duration: int = 0  # seconds
    early_surrender: bool = False
    raw_json: dict = json_field(dict)
    fetched_at: datetime = dt_field(default_now=True)


class PlayerMatchStats(SQLModel, table=True):
    match_id: str = Field(foreign_key="riotmatch.match_id", primary_key=True)
    player_id: int = Field(foreign_key="player.id", primary_key=True)
    champion_key: int
    team_id: int
    win: bool
    kills: int = 0
    deaths: int = 0
    assists: int = 0
    team_kills: int = 0
    cs: int = 0
    gold: int = 0
    damage_to_champs: int = 0
    vision_score: int = 0
    game_duration: int = 0
    queue_id: int = 0
    is_challenge: bool = False
    challenge_game_id: int | None = Field(default=None, foreign_key="challengegame.id")


DEFAULT_QUEUE_IDS = [400, 420, 440, 490]  # Normal Draft, Ranked Solo/Duo, Flex, Quickplay


class AppSettings(SQLModel, table=True):
    id: int = Field(default=1, primary_key=True)
    challenge_mode: bool = True
    active_run_id: int | None = Field(default=None, foreign_key="run.id")
    allowed_queue_ids: list[int] = json_field(lambda: list(DEFAULT_QUEUE_IDS))
    poll_interval_seconds: int = 90
    remake_threshold_seconds: int = 300
    last_used_player_ids: list[int] = json_field()
    last_sync_at: datetime | None = dt_field()
    last_sync_error: str | None = None
