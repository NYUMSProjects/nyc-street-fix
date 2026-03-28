from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    gemini_api_key: str = ""
    google_maps_api_key: str = ""
    mta_api_key: str = ""
    nyc_open_data_app_token: str = ""
    gemini_model: str = "gemini-2.5-flash"
    log_level: str = "INFO"
    elevator_cache_ttl: int = 300  # 5 minutes in seconds


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
