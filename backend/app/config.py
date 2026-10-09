from functools import lru_cache
from pathlib import Path

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
    # Run migrations and import champions (if none are cached) on startup. Tests turn this off.
    startup_tasks: bool = True

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
