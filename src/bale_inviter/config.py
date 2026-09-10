from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All runtime settings come from environment variables (and optional .env)."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    database_url: str = "sqlite:///./data/bale.db"
    bale_account: str = ""
    bale_bot_token: str = ""
    group_id: str = ""
    invite_link: str = ""
    invite_interval: int = 5
    max_retries: int = 3
    job_retry_delay_seconds: int = 60
    log_level: str = "INFO"
    log_dir: str = "./logs"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
