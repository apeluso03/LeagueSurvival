from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(BACKEND_DIR.parent / ".env", BACKEND_DIR / ".env"),
        extra="ignore",
    )

    riot_api_key: str = ""
    database_url: str = f"sqlite:///{(BACKEND_DIR / 'survival.db').as_posix()}"
    cors_origins: str = "http://localhost:5173"
    ddragon_base_url: str = "https://ddragon.leagueoflegends.com"
    # The game client's Live Client Data API, only up while this PC is in a game. "off" turns it off.
    live_client_url: str = "https://127.0.0.1:2999"
    # Run migrations and import champions (if none are cached) on startup. Tests turn this off.
    startup_tasks: bool = True

    @field_validator("riot_api_key")
    @classmethod
    def _key_off(cls, v: str) -> str:
        # RIOT_API_KEY=off (or none/disabled) turns Riot calls off even when .env has a key.
        # Handy for test servers; on Windows an empty value can't override .env.
        return "" if v.strip().lower() in ("off", "none", "disabled") else v.strip()

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
