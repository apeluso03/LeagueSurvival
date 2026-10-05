"""Request and response models for the API."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

# --- settings ---


class SettingsOut(BaseModel):
    challenge_mode: bool
    active_run_id: int | None
    allowed_queue_ids: list[int]
    poll_interval_seconds: int
    remake_threshold_seconds: int
    last_used_player_ids: list[int]
    riot_api_key_set: bool


class SettingsPatch(BaseModel):
    challenge_mode: bool | None = None
    active_run_id: int | None = None
    allowed_queue_ids: list[int] | None = None
    poll_interval_seconds: int | None = Field(default=None, ge=30)
    remake_threshold_seconds: int | None = Field(default=None, ge=0)
    last_used_player_ids: list[int] | None = None
    # When turning challenge mode off with a pending game: void it (true) or keep it pending (false).
    void_pending: bool = False


# --- players ---


class PlayerIn(BaseModel):
    display_name: str = Field(min_length=1, max_length=50)
    riot_game_name: str | None = None
    riot_tag_line: str | None = None
    platform: str = "na1"
    region: str = "americas"


class PlayerPatch(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=50)
    riot_game_name: str | None = None
    riot_tag_line: str | None = None
    platform: str | None = None
    region: str | None = None


# --- runs and pool ---


class RunIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    options_per_player: Literal[3, 4] = 3
    # None = full champion list
    champion_ids: list[str] | None = None


class RunOut(BaseModel):
    id: int
    name: str
    status: str
    options_per_player: int
    win_count: int
    current_streak: int
    best_streak: int
    started_at: datetime
    ended_at: datetime | None
    alive_count: int
    total_count: int
    tokens_available: int
    pending_game_id: int | None
    games_played: int


class PoolEntryOut(BaseModel):
    champion_id: str
    key: int
    name: str
    title: str
    tags: list[str]
    image_url: str
    status: str
    eliminated_at: datetime | None
    eliminated_in_game_id: int | None
    eliminated_by_player_id: int | None


# --- spins and games ---


class SpinIn(BaseModel):
    player_ids: list[int]


class AssignmentOut(BaseModel):
    player_id: int
    options: list[str]
    played_champion_id: str | None = None
    played_option_index: int | None = None


class MatchPlayerOut(BaseModel):
    player_id: int
    champion_id: str | None
    team_id: int
    win: bool
    kills: int
    deaths: int
    assists: int
    in_options: bool


class MatchSummaryOut(BaseModel):
    match_id: str
    queue_id: int
    game_start: datetime | None
    game_duration: int
    early_surrender: bool
    players: list[MatchPlayerOut]


class GameOut(BaseModel):
    id: int
    run_id: int
    created_at: datetime
    status: str
    result_source: str | None
    riot_match_id: str | None
    resolved_at: datetime | None
    void_reason: str | None
    assignments: list[AssignmentOut]
    eliminated: list[str]  # champions eliminated by this game's result
    tokens_earned: list[int]  # player ids that earned a token in this game
    needs_review: bool = False
    review_reason: str | None = None
    match: MatchSummaryOut | None = None  # the linked Riot match, or the one waiting for review


class SpinOut(BaseModel):
    practice: bool
    game: GameOut | None
    assignments: list[AssignmentOut]


class PickIn(BaseModel):
    player_id: int
    option_index: int | None = None
    champion_id: str | None = None


class AssignmentsPatch(BaseModel):
    picks: list[PickIn]


class ReviewIn(BaseModel):
    action: Literal["accept", "reject"]


class ResultIn(BaseModel):
    result: Literal["win", "loss", "void"]
    reason: str | None = None


# --- tokens ---


class TokenUseIn(BaseModel):
    champion_id: str


# --- riot and stats ---


class PlayerOut(BaseModel):
    id: int
    display_name: str
    riot_game_name: str | None
    riot_tag_line: str | None
    puuid: str | None
    platform: str
    region: str
    created_at: datetime
    # Set when a Riot ID lookup was attempted on this request and failed for a reason other than "not found".
    link_error: str | None = None


class RiotStatusOut(BaseModel):
    key_set: bool
    key_valid: bool | None  # None when not checked (no key)
    message: str | None
    last_sync_at: datetime | None
    last_sync_error: str | None


class MatchOutcomeOut(BaseModel):
    game_id: int
    status: str
    message: str
    match_id: str | None


class SyncOut(BaseModel):
    players_synced: int
    new_matches: int
    errors: list[str]
    games: list[MatchOutcomeOut] = []


class ChampionStatsOut(BaseModel):
    champion_id: str
    games: int
    wins: int
    win_rate: float
    kda: float | None


class PlayerStatsOut(BaseModel):
    player_id: int
    games: int
    wins: int
    losses: int
    win_rate: float | None
    detailed_games: int
    avg_kills: float | None
    avg_deaths: float | None
    avg_assists: float | None
    kda: float | None
    kill_participation: float | None
    cs_per_min: float | None
    damage_per_min: float | None
    vision_per_min: float | None
    best_champions: list[ChampionStatsOut]
    eliminated_champions: list[str]
