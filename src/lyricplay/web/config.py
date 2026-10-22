"""Web player settings, loaded from ``LYRICPLAY_WEB_*`` environment variables."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    host: str = "127.0.0.1"
    port: int = 8765
    open_browser: bool = True

    model_config = SettingsConfigDict(
        env_prefix="LYRICPLAY_WEB_",
        env_file=".env",
        extra="ignore",
    )


settings = Settings()
