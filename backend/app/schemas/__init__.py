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


class ResultIn(BaseModel):
    result: Literal["win", "loss", "void"]
    reason: str | None = None


# --- tokens ---


class TokenUseIn(BaseModel):
    champion_id: str
