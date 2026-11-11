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
    # The built frontend (frontend/dist) to serve from the same address as the API, when hosted.
    # Empty: don't serve it (local development uses the Vite dev server).
    frontend_dist: str = ""
    # The site's own address (e.g. https://hardcoredraft.gg), for links in Discord posts and as the
    # Discord sign-in return address. Empty: taken from each request; posts go without links.
    public_url: str = ""
    # When a new daily puzzle starts (midnight in this time zone, SPEC 20).
    daily_timezone: str = "America/New_York"
    # The Discord bot (SPEC 19), from the Discord Developer Portal. All four, or the bot stays off.
    discord_app_id: str = ""
    discord_public_key: str = ""
    discord_bot_token: str = ""
    discord_client_secret: str = ""

    @field_validator("riot_api_key")
    @classmethod
    def _key_off(cls, v: str) -> str:
        # RIOT_API_KEY=off (or none/disabled) turns Riot calls off even when .env has a key.
        # Handy for test servers; on Windows an empty value can't override .env.
        return "" if v.strip().lower() in ("off", "none", "disabled") else v.strip()

    @field_validator("database_url")
    @classmethod
    def _db_driver(cls, v: str) -> str:
        # Hosts hand out "postgres://..." or "postgresql://..."; SQLAlchemy needs the driver named.
        v = v.strip()
        for prefix in ("postgres://", "postgresql://"):
            if v.startswith(prefix):
                return "postgresql+psycopg://" + v[len(prefix):]
        return v

    @property
    def discord_enabled(self) -> bool:
        return all((self.discord_app_id, self.discord_public_key, self.discord_bot_token, self.discord_client_secret))

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
